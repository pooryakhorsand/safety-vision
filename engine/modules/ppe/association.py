"""
Which person does each piece of equipment belong to?

Rules (ported from the prototype, plus the body-zone check):
  1. the item must lie mostly INSIDE the person's box   (min_contain)
  2. the item must sit in the right part of the body    (helmet: top, shoes: bottom)
  3. one item belongs to ONE person: the one whose horizontal centre is closest
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from engine.core.config import PpeConfig
from engine.core.frame import Box


def split_name(name: str, missing_prefixes: Sequence[str]) -> tuple[str, bool]:
    """'no_helmet' -> ('helmet', True)   'helmet' -> ('helmet', False)"""
    lower = name.lower()
    for prefix in missing_prefixes:
        if lower.startswith(prefix):
            return lower[len(prefix) :], True
    return lower, False


def zone_for(item: str, zones: dict) -> tuple[float, float] | None:
    """Body zone for an item: the config key is matched as a substring of the item name."""
    for key, zone in zones.items():
        if key in item:
            return float(zone[0]), float(zone[1])
    return None


def assign_equipment(
    persons: Sequence[tuple[int, Box]],
    equipment: Sequence[tuple[str, float, Box]],
    config: PpeConfig,
) -> dict[int, list[tuple[str, float, Box]]]:
    """
    persons:   (track_id, box)
    equipment: (class_name, confidence, box)
    returns    {track_id: [(class_name, confidence, box), ...]}   items nobody owns are dropped
    """
    result: dict[int, list] = defaultdict(list)
    for name, conf, box in equipment:
        ex1, ey1, ex2, ey2 = box
        area = max(1e-6, (ex2 - ex1) * (ey2 - ey1))
        centre_x, centre_y = (ex1 + ex2) / 2, (ey1 + ey2) / 2
        item, _ = split_name(name, config.missing_prefixes)
        zone = zone_for(item, config.zones)

        best_id, best_score = None, float("-inf")
        for track_id, (px1, py1, px2, py2) in persons:
            iw = min(ex2, px2) - max(ex1, px1)
            ih = min(ey2, py2) - max(ey1, py1)
            if iw <= 0 or ih <= 0:
                continue
            contain = iw * ih / area
            if contain < config.min_contain:
                continue
            height = max(1.0, py2 - py1)
            width = max(1.0, px2 - px1)
            if zone is not None:
                relative_y = (centre_y - py1) / height
                if not (zone[0] - config.zone_margin <= relative_y <= zone[1] + config.zone_margin):
                    continue
            score = contain - 0.5 * abs(centre_x - (px1 + px2) / 2) / width
            if score > best_score:
                best_id, best_score = track_id, score
        if best_id is not None:
            result[best_id].append((name, conf, box))
    return result

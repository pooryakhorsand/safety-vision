"""
Temporal voting: stops labels flickering.

For every person and every item (helmet, vest, ...) we keep the last N observations:
    +1 = seen WITH the item,  -1 = seen WITHOUT it ("no_helmet"),  0 = not seen
The state only changes when enough frames agree (min_votes). A tie counts as a
violation (safety first).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence

from engine.core.config import PpeConfig
from engine.core.frame import Box
from engine.modules.ppe.association import split_name

OK, BAD = "ok", "bad"
FORGET_AFTER_FRAMES = 150


class PpeVoter:
    def __init__(self, config: PpeConfig):
        self.config = config
        self._votes: dict[int, dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=config.vote_window))
        )
        self._state: dict[int, dict[str, str]] = defaultdict(dict)
        self._confidence: dict[int, dict[str, float]] = defaultdict(dict)
        self._last_seen: dict[int, int] = {}

    def update(self, track_id: int, items: Sequence[tuple[str, float, Box]], frame_index: int) -> dict[str, str]:
        """items = the equipment assigned to this person in this frame. Returns {item: 'ok'|'bad'}."""
        best: dict[str, tuple[float, int]] = {}  # item -> (confidence, +1 / -1)
        for name, conf, _ in items:
            item, missing = split_name(name, self.config.missing_prefixes)
            if item not in best or conf > best[item][0]:
                best[item] = (conf, -1 if missing else 1)

        votes = self._votes[track_id]
        for item in set(votes) | set(best):
            votes[item].append(best[item][1] if item in best else 0)
            if item in best:
                self._confidence[track_id][item] = best[item][0]
            ok, bad = votes[item].count(1), votes[item].count(-1)
            if bad >= self.config.min_votes and bad >= ok:
                self._state[track_id][item] = BAD
            elif ok >= self.config.min_votes and ok > bad:
                self._state[track_id][item] = OK
        self._last_seen[track_id] = frame_index
        return self._state[track_id]

    def confidence(self, track_id: int, item: str) -> float:
        return self._confidence[track_id].get(item, 0.0)

    def forget_stale(self, frame_index: int) -> None:
        for track_id in [t for t, seen in self._last_seen.items() if frame_index - seen > FORGET_AFTER_FRAMES]:
            self._votes.pop(track_id, None)
            self._state.pop(track_id, None)
            self._confidence.pop(track_id, None)
            self._last_seen.pop(track_id, None)

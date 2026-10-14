"""
Drawing on the picture: person corners, tags and equipment boxes.
DISPLAY ONLY: nothing here decides anything. Decisions come from the modules.

Detection always runs on the ORIGINAL frame. render_frame() makes a separate display
copy (never larger than the original) and draws the overlay on it.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from engine.core.config import EngineConfig
from engine.core.frame import Box, FrameContext, Label

GREEN = (90, 220, 90)
RED = (70, 70, 255)
WHITE = (255, 255, 255)
GREY = (170, 170, 170)
FONT = cv2.FONT_HERSHEY_DUPLEX


def output_size(frame_width: int, frame_height: int, max_long_side: int) -> tuple[int, int]:
    """Display size: never upscaled, always even (H.264 needs even sizes)."""
    scale = min(1.0, max_long_side / max(frame_width, frame_height))
    return int(round(frame_width * scale)) // 2 * 2, int(round(frame_height * scale)) // 2 * 2


class Overlay:
    """Knows the display size and how to draw one person, one equipment box, the REC mark."""

    def __init__(self, width: int, height: int, config: EngineConfig):
        self.width, self.height = width, height
        self.scale = max(width, height) / 1280  # lines and text grow with the picture
        self.item_colors = config.modules.ppe.item_colors
        self.missing_prefixes = config.modules.ppe.missing_prefixes

    # ------------------------------------------------------------ colours
    def label_color(self, name: str) -> tuple[int, int, int]:
        lower = name.lower()
        missing = False
        for prefix in self.missing_prefixes:
            if lower.startswith(prefix):
                lower, missing = lower[len(prefix) :], True
                break
        for key, (has_color, missing_color) in self.item_colors.items():
            if key in lower:
                return tuple(missing_color if missing else has_color)
        return RED if missing else GREEN

    # ------------------------------------------------------------ pieces
    def equipment_box(self, img, name: str, box: Box) -> None:
        x1, y1, x2, y2 = (int(v) for v in box)
        cv2.rectangle(img, (x1, y1), (x2, y2), self.label_color(name), max(2, int(1.5 * self.scale)), cv2.LINE_AA)

    def person(self, img, box: Box, track_id: int, labels: Sequence[Label], occupied: list) -> None:
        x1, y1, x2, y2 = (int(v) for v in box)
        bad = any(label.violation for label in labels)
        color = RED if bad else GREEN
        self._corners(img, x1, y1, x2, y2, color)
        parts = [(f"Person #{track_id}", WHITE)]
        if labels:
            parts.append(("|", GREY))
            parts += [(label.name, self.label_color(label.name)) for label in labels]
        self._tag(img, x1, y1, parts, color, occupied)

    # ------------------------------------------------------------ internals
    def _text(self, img, text: str, x: int, y: int, color=WHITE, size: float = 0.7) -> None:
        font_scale = size * self.scale
        thickness = max(1, int(round(1.6 * self.scale)))
        cv2.putText(img, text, (x, y), FONT, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
        cv2.putText(img, text, (x, y), FONT, font_scale, color, thickness, cv2.LINE_AA)

    def _corners(self, img, x1, y1, x2, y2, color) -> None:
        t = max(2, int(round(2.5 * self.scale)))
        length = max(12, int(min(x2 - x1, y2 - y1) * 0.18))
        for px, py, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
            cv2.line(img, (px, py), (px + dx * length, py), color, t, cv2.LINE_AA)
            cv2.line(img, (px, py), (px, py + dy * length), color, t, cv2.LINE_AA)

    def _place_tag(self, x: int, y_ref: int, w: int, h: int, occupied: list) -> tuple[int, int, int, int]:
        """Put the tag above the box; move it up (then below) until it touches no other tag."""
        left = int(max(0, min(x, self.width - w)))
        step = h + 2
        candidates = [y_ref - h - 2 - k * step for k in range(5)] + [y_ref + 2 + k * step for k in range(5)]
        for top in candidates:
            if top < 0 or top + h > self.height:
                continue
            rect = (left, top, left + w, top + h)
            if not any(
                not (rect[2] <= o[0] or o[2] <= rect[0] or rect[3] <= o[1] or o[3] <= rect[1]) for o in occupied
            ):
                return rect
        top = int(min(max(candidates[0], 0), self.height - h))
        return left, top, left + w, top + h

    def _tag(self, img, x: int, y_top: int, parts, bar_color, occupied: list) -> None:
        s = self.scale
        font_scale, thickness = 0.5 * s, max(1, int(round(1.2 * s)))
        pad, gap = int(6 * s), int(8 * s)
        sizes = [cv2.getTextSize(text, FONT, font_scale, thickness)[0] for text, _ in parts]
        text_h = max(size[1] for size in sizes)
        w = min(sum(size[0] for size in sizes) + gap * (len(parts) - 1) + 2 * pad + int(4 * s), self.width)
        h = text_h + 2 * pad

        x1, y1, x2, y2 = self._place_tag(x, y_top, w, h, occupied)
        occupied.append((x1, y1, x2, y2))
        roi = img[y1:y2, x1:x2]
        cv2.addWeighted(np.zeros_like(roi), 0.6, roi, 0.4, 0, roi)  # translucent dark bar
        cv2.rectangle(img, (x1, y1), (x1 + int(3 * s) + 1, y2), bar_color, -1)
        cx, cy = x1 + int(4 * s) + pad, y1 + pad + text_h
        for (text, color), (text_w, _) in zip(parts, sizes):
            cv2.putText(img, text, (cx, cy), FONT, font_scale, color, thickness, cv2.LINE_AA)
            cx += text_w + gap


def _inside(box: Box, outer: Box) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def render_frame(ctx: FrameContext, overlay: Overlay, *, draw_equipment: bool = True):
    """Build the picture people look at: a display-size copy of the frame with the overlay drawn on it."""
    height, width = ctx.image.shape[:2]
    sx, sy = overlay.width / width, overlay.height / height
    if (overlay.width, overlay.height) != (width, height):
        image = cv2.resize(ctx.image, (overlay.width, overlay.height), interpolation=cv2.INTER_AREA)
    else:
        image = ctx.image.copy()

    def scaled(box: Box) -> Box:
        return box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy

    if draw_equipment:
        person_boxes = [t.box for t in ctx.persons]
        for det in ctx.detections.get("equipment", []):
            if any(_inside(det.box, p) for p in person_boxes):
                overlay.equipment_box(image, det.class_name, scaled(det.box))

    labels_by_track: dict[int, list[Label]] = {}
    for obs in ctx.observations:
        if obs.labels and obs.track_id not in labels_by_track:
            labels_by_track[obs.track_id] = obs.labels

    occupied: list = []
    for track in sorted(ctx.persons, key=lambda t: t.box[1]):
        overlay.person(image, scaled(track.box), track.track_id, labels_by_track.get(track.track_id, []), occupied)

    return image


class FrameRenderer:
    """Owns the overlay for the display size and renders frames with the engine settings."""

    def __init__(self, config: EngineConfig):
        self.config = config
        self._size: tuple[int, int] | None = None
        self.overlay: Overlay | None = None

    def size_for(self, image) -> tuple[int, int]:
        height, width = image.shape[:2]
        return output_size(width, height, self.config.render.max_long_side)

    def render(self, ctx: FrameContext):
        size = self.size_for(ctx.image)
        if size != self._size:  # first frame, or the camera changed resolution
            self._size = size
            self.overlay = Overlay(size[0], size[1], self.config)
        return render_frame(ctx, self.overlay)

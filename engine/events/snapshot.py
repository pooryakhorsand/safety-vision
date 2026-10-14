"""
Evidence picture for an event: the frame, the person marked, as JPEG bytes.
Made with the same overlay as the live view.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2

from engine.core.config import EngineConfig
from engine.core.frame import Box, FrameContext, Label
from engine.render.overlay import Overlay, output_size


def make_snapshot(ctx: FrameContext, track_id: int, box: Box, labels: Sequence[Label], config: EngineConfig) -> bytes:
    """JPEG of the frame with ONE person marked. Longest side is limited by events.snapshot_max_side."""
    height, width = ctx.image.shape[:2]
    out_w, out_h = output_size(width, height, config.events.snapshot_max_side)
    sx, sy = out_w / width, out_h / height

    image = (
        cv2.resize(ctx.image, (out_w, out_h), interpolation=cv2.INTER_AREA)
        if (out_w, out_h) != (width, height)
        else ctx.image.copy()
    )

    overlay = Overlay(out_w, out_h, config)
    overlay.person(image, (box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy), track_id, labels, [])

    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, config.events.snapshot_quality])
    if not ok:
        raise RuntimeError("could not encode the snapshot")
    return encoded.tobytes()

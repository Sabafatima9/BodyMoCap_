"""Skeleton overlay on preview image or GPU handler (FR-030–032)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..core.landmarks import POSE_CONNECTIONS
from ..core.types import Landmark


def confidence_color(confidence: float, threshold: float = 0.5) -> Tuple[int, int, int]:
    """BGR color: green high, yellow mid, red low."""
    if confidence >= threshold + 0.2:
        return (0, 220, 0)
    if confidence >= threshold:
        return (0, 200, 220)
    return (0, 0, 220)


def draw_skeleton_opencv(
    frame_bgr: Any,
    landmarks: Dict[str, Landmark],
    threshold: float = 0.5,
    enabled: bool = True,
) -> Any:
    """Draw joints + bones onto a BGR frame copy."""
    if not enabled or frame_bgr is None:
        return frame_bgr
    try:
        import cv2
        import numpy as np
    except ImportError:
        return frame_bgr

    out = frame_bgr.copy()
    h, w = out.shape[:2]

    def to_px(lm: Landmark) -> Tuple[int, int]:
        # Landmarks may be normalized 0..1 or world-ish; detect
        x, y = lm.position.x, lm.position.y
        if abs(x) <= 1.5 and abs(y) <= 1.5:
            # Treat as normalized image coords centered or 0..1
            if x < 0 or y < 0 or x > 1.0 or y > 1.0:
                # centered / y-up world → project roughly
                px = int((x + 0.5) * w)
                py = int((1.0 - y) * h) if y <= 2.0 else int(y * h)
            else:
                px = int(x * w)
                py = int(y * h)
        else:
            px = int(x)
            py = int(y)
        return px, py

    pts: Dict[str, Tuple[int, int]] = {}
    for name, lm in landmarks.items():
        if not lm.valid and lm.confidence < threshold:
            continue
        pts[name] = to_px(lm)
        color = confidence_color(lm.confidence, threshold)
        cv2.circle(out, pts[name], 4, color, -1)

    for a, b in POSE_CONNECTIONS:
        if a in pts and b in pts:
            ca = landmarks[a].confidence if a in landmarks else 0.0
            cb = landmarks[b].confidence if b in landmarks else 0.0
            color = confidence_color(min(ca, cb), threshold)
            cv2.line(out, pts[a], pts[b], color, 2)

    return out


_DRAW_HANDLE = None


def register_viewport_draw_handler(draw_callback) -> Any:
    """Register SpaceView3D draw handler; returns handle."""
    global _DRAW_HANDLE
    try:
        import bpy
        import bpy.types

        if _DRAW_HANDLE is not None:
            unregister_viewport_draw_handler()
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback, (), "WINDOW", "POST_VIEW"
        )
        return _DRAW_HANDLE
    except Exception:
        return None


def unregister_viewport_draw_handler() -> None:
    global _DRAW_HANDLE
    if _DRAW_HANDLE is None:
        return
    try:
        import bpy

        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
    except Exception:
        pass
    _DRAW_HANDLE = None

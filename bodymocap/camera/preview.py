"""Update Blender Image datablock from camera frames (FR-011)."""

from __future__ import annotations

from typing import Any, Optional, Tuple

PREVIEW_IMAGE_NAME = "BodyMocap_Preview"


def bgr_to_rgba_pixels(frame_bgr: Any) -> Optional[Tuple[Any, int, int]]:
    """BGR uint8 frame → (flat float32 RGBA, width, height) in Blender pixel order.

    Pure numpy, so the capture worker thread can do it off the UI thread.
    """
    try:
        import numpy as np
    except ImportError:
        return None
    if frame_bgr is None:
        return None
    arr = np.asarray(frame_bgr)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    h, w = arr.shape[:2]
    rgba = np.empty((h, w, 4), dtype=np.float32)
    # BGR → RGB, flip vertically for Blender image coords, alpha = 1
    rgba[:, :, :3] = arr[::-1, :, 2::-1].astype(np.float32) * (1.0 / 255.0)
    rgba[:, :, 3] = 1.0
    return rgba.ravel(), w, h


def rgba_pixels_to_blender_image(flat: Any, w: int, h: int, image_name: str = PREVIEW_IMAGE_NAME) -> Optional[object]:
    """Upload prepared RGBA pixels into the preview Image datablock (main thread only)."""
    try:
        import bpy
    except ImportError:
        return None
    img = bpy.data.images.get(image_name)
    if img is None:
        img = bpy.data.images.new(image_name, width=w, height=h, alpha=True)
    elif img.size[0] != w or img.size[1] != h:
        bpy.data.images.remove(img)
        img = bpy.data.images.new(image_name, width=w, height=h, alpha=True)
    img.pixels.foreach_set(flat)
    img.update()
    return img


def numpy_bgr_to_blender_image(frame_bgr: Any, image_name: str = PREVIEW_IMAGE_NAME) -> Optional[object]:
    """Push a BGR uint8 frame into a Blender Image (viewer/preview)."""
    prepared = bgr_to_rgba_pixels(frame_bgr)
    if prepared is None:
        return None
    flat, w, h = prepared
    return rgba_pixels_to_blender_image(flat, w, h, image_name)


def ensure_preview_area() -> None:
    """Best-effort: tag redraw on image editors showing preview."""
    try:
        import bpy

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "IMAGE_EDITOR":
                    area.tag_redraw()
    except Exception:
        pass

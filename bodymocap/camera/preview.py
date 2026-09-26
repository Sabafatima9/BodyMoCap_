"""Update Blender Image datablock from camera frames (FR-011)."""

from __future__ import annotations

from typing import Any, Optional

PREVIEW_IMAGE_NAME = "BodyMocap_Preview"


def numpy_bgr_to_blender_image(frame_bgr: Any, image_name: str = PREVIEW_IMAGE_NAME) -> Optional[object]:
    """Push a BGR uint8 frame into a Blender Image (viewer/preview)."""
    try:
        import bpy
        import numpy as np
    except ImportError:
        return None

    if frame_bgr is None:
        return None

    arr = np.asarray(frame_bgr)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None

    h, w = arr.shape[:2]
    # BGR → RGB float 0..1, flip vertically for Blender image coords
    rgb = arr[:, :, ::-1].astype(np.float32) / 255.0
    rgb = np.flipud(rgb)
    # RGBA
    alpha = np.ones((h, w, 1), dtype=np.float32)
    rgba = np.concatenate([rgb, alpha], axis=2)
    flat = rgba.ravel()

    img = bpy.data.images.get(image_name)
    if img is None:
        img = bpy.data.images.new(image_name, width=w, height=h, alpha=True)
    elif img.size[0] != w or img.size[1] != h:
        bpy.data.images.remove(img)
        img = bpy.data.images.new(image_name, width=w, height=h, alpha=True)

    img.pixels.foreach_set(flat)
    img.update()
    return img


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

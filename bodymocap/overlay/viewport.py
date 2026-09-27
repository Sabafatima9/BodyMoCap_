"""Live camera picture-in-picture and 3D ghost skeleton in the 3D Viewport (FR-011, FR-030–032).

Two ``SpaceView3D`` draw handlers are registered while capture runs:

* ``POST_PIXEL`` – the camera frame (with the OpenCV skeleton overlay) in a corner
  of every 3D viewport, plus a status strip (tracking state, fps, REC timer).
  With the mock backend there is no frame, so the 2D skeleton is drawn instead.
* ``POST_VIEW`` – the tracked body as a 3D stick figure in world space, scaled and
  anchored to the driven rig, so the performer's skeleton and the rig's bones can
  be compared directly while moving in 3D.

All state is pushed from the capture loop through :func:`update_overlay`; the
handlers only read it, so they stay cheap and never touch the camera.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..camera.preview import PREVIEW_IMAGE_NAME
from ..core.landmarks import POSE_CONNECTIONS

_HANDLES: Dict[str, Any] = {"pixel": None, "view": None}

_STATE: Dict[str, Any] = {
    "image_name": PREVIEW_IMAGE_NAME,
    "has_image": False,
    "landmarks_2d": {},  # name -> (x, y, confidence, valid); x in -0.5..0.5, y in 0..1 (up)
    "ghost": [],  # (name, (x, y, z), confidence, valid) in world space
    "status": "",
    "fps": 0.0,
    "recording": False,
    "paused": False,
    "record_started": 0.0,
    "frame_count": 0,
    "threshold": 0.5,
    "message": "",
}

_MARGIN = 12
_HEADER = 22


def update_overlay(
    landmarks_2d: Optional[Dict[str, Tuple[float, float, float, bool]]] = None,
    ghost: Optional[List[Tuple[str, Tuple[float, float, float], float, bool]]] = None,
    **kwargs: Any,
) -> None:
    if landmarks_2d is not None:
        _STATE["landmarks_2d"] = landmarks_2d
    if ghost is not None:
        _STATE["ghost"] = ghost
    _STATE.update(kwargs)


def clear_overlay_data() -> None:
    _STATE["landmarks_2d"] = {}
    _STATE["ghost"] = []
    _STATE["has_image"] = False
    _STATE["message"] = ""


def is_registered() -> bool:
    return _HANDLES["pixel"] is not None or _HANDLES["view"] is not None


def register_viewport_overlay() -> bool:
    try:
        import bpy
    except ImportError:
        return False
    if _HANDLES["pixel"] is None:
        _HANDLES["pixel"] = bpy.types.SpaceView3D.draw_handler_add(
            _draw_pip, (), "WINDOW", "POST_PIXEL"
        )
    if _HANDLES["view"] is None:
        _HANDLES["view"] = bpy.types.SpaceView3D.draw_handler_add(
            _draw_ghost, (), "WINDOW", "POST_VIEW"
        )
    tag_redraw_view3d()
    return True


def unregister_viewport_overlay() -> None:
    try:
        import bpy
    except ImportError:
        return
    for key in ("pixel", "view"):
        handle = _HANDLES.get(key)
        if handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
            except Exception:
                pass
            _HANDLES[key] = None
    clear_overlay_data()
    tag_redraw_view3d()


def tag_redraw_view3d() -> None:
    """Redraw every 3D viewport (overlay + sidebar panels)."""
    try:
        import bpy

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

def _confidence_rgba(confidence: float, threshold: float) -> Tuple[float, float, float, float]:
    if confidence >= threshold + 0.2:
        return (0.2, 0.9, 0.3, 0.95)
    if confidence >= threshold:
        return (0.95, 0.85, 0.2, 0.95)
    return (0.95, 0.25, 0.2, 0.9)


def _settings():
    try:
        import bpy

        return bpy.context.scene.bodymocap
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Picture-in-picture (POST_PIXEL)
# ---------------------------------------------------------------------------

def _visible_rect(context) -> Tuple[float, float, float, float]:
    """Region rectangle not covered by overlapping toolbar / sidebar / headers."""
    region = context.region
    left, right, top, bottom = 0.0, float(region.width), float(region.height), 0.0
    try:
        space = context.space_data
        overlap = context.preferences.system.use_region_overlap
        for r in context.area.regions:
            if r.width <= 1 or r.height <= 1:
                continue
            if r.type == "UI" and overlap and space.show_region_ui:
                right -= r.width
            elif r.type == "TOOLS" and overlap and space.show_region_toolbar:
                left += r.width
            elif r.type in ("HEADER", "TOOL_HEADER"):
                top -= r.height
    except Exception:
        pass
    return left, bottom, right, top


def _pip_rect(context, aspect: float, size: float, corner: str) -> Tuple[float, float, float, float]:
    left, bottom, right, top = _visible_rect(context)
    avail_w = max(right - left, 1.0)
    avail_h = max(top - bottom, 1.0)
    pip_w = max(120.0, avail_w * size)
    pip_h = pip_w / max(aspect, 1e-3)
    max_h = avail_h - 2 * _MARGIN - _HEADER
    if pip_h > max_h > 60:
        pip_h = max_h
        pip_w = pip_h * aspect
    if corner.endswith("RIGHT"):
        x0 = right - _MARGIN - pip_w
    else:
        x0 = left + _MARGIN
    if corner.startswith("TOP"):
        y0 = top - _MARGIN - _HEADER - pip_h
    else:
        y0 = bottom + _MARGIN
    return x0, y0, pip_w, pip_h


def _draw_rect(shader, x0, y0, w, h, color, filled=True):
    from gpu_extras.batch import batch_for_shader

    coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    shader.uniform_float("color", color)
    batch = batch_for_shader(shader, "TRI_FAN" if filled else "LINE_LOOP", {"pos": coords})
    batch.draw(shader)


def _draw_lines_2d(shader, segments: Sequence[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, ...]]]):
    """Draw coloured 2D line segments: (a, b, rgba)."""
    import gpu
    from gpu_extras.batch import batch_for_shader

    if not segments:
        return
    coords = []
    colors = []
    for a, b, rgba in segments:
        coords.extend([a, b])
        colors.extend([rgba, rgba])
    batch = batch_for_shader(shader, "LINES", {"pos": coords, "color": colors})
    batch.draw(shader)


def _skeleton_segments_2d(x0, y0, w, h, threshold) -> Tuple[list, list]:
    """2D skeleton in pip pixel coords from normalized landmarks."""
    lms = _STATE.get("landmarks_2d") or {}
    pts = {}
    for name, (x, y, conf, valid) in lms.items():
        if not valid and conf < threshold:
            continue
        pts[name] = ((x0 + (x + 0.5) * w, y0 + y * h), conf)
    segments = []
    for a, b in POSE_CONNECTIONS:
        if a in pts and b in pts:
            conf = min(pts[a][1], pts[b][1])
            segments.append((pts[a][0], pts[b][0], _confidence_rgba(conf, threshold)))
    joints = [(p, _confidence_rgba(c, threshold)) for p, c in pts.values()]
    return segments, joints


def _status_text() -> Tuple[str, Tuple[float, float, float, float]]:
    if _STATE.get("recording"):
        elapsed = max(0.0, time.time() - float(_STATE.get("record_started") or time.time()))
        state = "PAUSED" if _STATE.get("paused") else "REC"
        text = f"{state}  {int(elapsed // 60):02d}:{int(elapsed % 60):02d}   {_STATE.get('frame_count', 0)} frames"
        return text, (1.0, 0.3, 0.3, 1.0)
    fps = _STATE.get("fps") or 0.0
    status = _STATE.get("status") or "-"
    text = f"BodyMocap   tracking {status}   {fps:.0f} fps"
    color = (0.35, 0.95, 0.45, 1.0) if status == "OK" else (0.95, 0.8, 0.3, 1.0)
    return text, color


def _draw_text(x: float, y: float, text: str, color, size: int = 12) -> None:
    import blf

    font_id = 0
    try:
        blf.size(font_id, size)
    except TypeError:  # Blender < 4.0 signature
        blf.size(font_id, size, 72)
    blf.color(font_id, *color)
    blf.position(font_id, x, y, 0)
    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.8)
    blf.shadow_offset(font_id, 1, -1)
    blf.draw(font_id, text)
    blf.disable(font_id, blf.SHADOW)


def _draw_pip() -> None:
    try:
        import bpy
        import gpu

        settings = _settings()
        if settings is None or not settings.camera_active or not settings.show_camera_in_viewport:
            return
        context = bpy.context
        if context.region is None or context.region.type != "WINDOW":
            return

        image = bpy.data.images.get(_STATE["image_name"]) if _STATE.get("has_image") else None
        texture = None
        aspect = 4.0 / 3.0
        if image is not None and image.size[0] > 0 and image.size[1] > 0:
            try:
                texture = gpu.texture.from_image(image)
                aspect = image.size[0] / image.size[1]
            except Exception:
                texture = None

        x0, y0, w, h = _pip_rect(context, aspect, settings.viewport_camera_size, settings.viewport_camera_corner)
        threshold = float(_STATE.get("threshold", 0.5))

        gpu.state.blend_set("ALPHA")
        flat = gpu.shader.from_builtin("UNIFORM_COLOR")

        # Header strip
        _draw_rect(flat, x0, y0 + h, w, _HEADER, (0.05, 0.05, 0.06, 0.85))

        if texture is not None:
            from gpu_extras.batch import batch_for_shader

            img_shader = gpu.shader.from_builtin("IMAGE")
            img_shader.bind()
            img_shader.uniform_sampler("image", texture)
            batch = batch_for_shader(
                img_shader,
                "TRI_FAN",
                {
                    "pos": [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)],
                    "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)],
                },
            )
            batch.draw(img_shader)
        else:
            _draw_rect(flat, x0, y0, w, h, (0.08, 0.08, 0.1, 0.9))

        if texture is None or settings.pose_backend == "MOCK":
            segments, joints = _skeleton_segments_2d(x0, y0, w, h, threshold)
            color_shader = gpu.shader.from_builtin("FLAT_COLOR")
            gpu.state.line_width_set(2.0)
            _draw_lines_2d(color_shader, segments)
            gpu.state.point_size_set(6.0)
            if joints:
                from gpu_extras.batch import batch_for_shader

                batch = batch_for_shader(
                    color_shader,
                    "POINTS",
                    {"pos": [p for p, _ in joints], "color": [c for _, c in joints]},
                )
                batch.draw(color_shader)

        # Border: red while recording
        border = (0.95, 0.2, 0.2, 1.0) if _STATE.get("recording") else (0.85, 0.85, 0.85, 0.6)
        gpu.state.line_width_set(2.0)
        _draw_rect(flat, x0, y0, w, h + _HEADER, border, filled=False)
        gpu.state.line_width_set(1.0)

        text, color = _status_text()
        _draw_text(x0 + 8, y0 + h + 6, text, color)
        message = _STATE.get("message")
        if message:
            _draw_text(x0 + 8, y0 + 8, message, (1.0, 1.0, 1.0, 0.95), size=11)

        gpu.state.blend_set("NONE")
    except Exception as exc:  # never let a draw error take down the viewport
        from ..utils.logging_util import log_warning

        log_warning(f"viewport overlay draw failed: {exc}")


# ---------------------------------------------------------------------------
# Ghost skeleton (POST_VIEW)
# ---------------------------------------------------------------------------

def _draw_ghost() -> None:
    try:
        import gpu
        from gpu_extras.batch import batch_for_shader

        settings = _settings()
        if settings is None or not settings.camera_active or not settings.show_ghost_skeleton:
            return
        ghost = _STATE.get("ghost") or []
        if not ghost:
            return
        threshold = float(_STATE.get("threshold", 0.5))
        pts = {name: (pos, conf) for name, pos, conf, valid in ghost if valid or conf >= threshold}
        coords, colors = [], []
        for a, b in POSE_CONNECTIONS:
            if a in pts and b in pts:
                rgba = _confidence_rgba(min(pts[a][1], pts[b][1]), threshold)
                coords.extend([pts[a][0], pts[b][0]])
                colors.extend([rgba, rgba])
        if not coords:
            return
        shader = gpu.shader.from_builtin("FLAT_COLOR")
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        gpu.state.line_width_set(3.0)
        batch_for_shader(shader, "LINES", {"pos": coords, "color": colors}).draw(shader)
        gpu.state.point_size_set(9.0)
        joint_coords = [p for p, _ in pts.values()]
        joint_colors = [_confidence_rgba(c, threshold) for _, c in pts.values()]
        batch_for_shader(shader, "POINTS", {"pos": joint_coords, "color": joint_colors}).draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.point_size_set(1.0)
        gpu.state.depth_test_set("LESS_EQUAL")
        gpu.state.blend_set("NONE")
    except Exception as exc:
        from ..utils.logging_util import log_warning

        log_warning(f"ghost skeleton draw failed: {exc}")

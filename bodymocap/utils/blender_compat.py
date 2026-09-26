"""Blender version checks, dependency status and API shims (FR-003, FR-004, FR-082).

Compatible with Blender 4.x and 5.x (incl. slotted Actions in 5.x and the
MediaPipe 0.x `solutions` vs 1.x `tasks` APIs).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# Official MediaPipe model used by the Tasks API backend.
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)
POSE_MODEL_NAME = "pose_landmarker_full.task"


def get_blender_version() -> Tuple[int, int, int]:
    try:
        import bpy

        v = bpy.app.version
        return (int(v[0]), int(v[1]), int(v[2]))
    except Exception:
        return (0, 0, 0)


def is_supported_blender(min_version: Tuple[int, int, int] = (4, 0, 0)) -> bool:
    ver = get_blender_version()
    if ver == (0, 0, 0):
        return False
    return ver >= min_version


def version_warning_message(min_version: Tuple[int, int, int] = (4, 0, 0)) -> str:
    ver = get_blender_version()
    return (
        f"BodyMocap requires Blender {min_version[0]}.{min_version[1]}+; "
        f"detected {ver[0]}.{ver[1]}.{ver[2]}"
    )


# --------------------------------------------------------------------------
# Slotted Actions (Blender 4.4+ / required in 5.x)
# --------------------------------------------------------------------------

def action_has_legacy_fcurves(action) -> bool:
    return hasattr(action, "fcurves")


def clear_action_fcurves(action) -> int:
    """Remove all keyframes from an Action. Returns count removed.

    Blender < 4.4/5.0 exposes ``action.fcurves`` directly. Blender 5.x uses
    slotted actions: layers -> strips -> channelbags -> fcurves.
    """
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        count = len(fcurves)
        for fc in list(fcurves):
            fcurves.remove(fc)
        return count

    removed = 0
    layers = getattr(action, "layers", None)
    if layers is None:
        return 0
    for layer in list(layers):
        for strip in list(layer.strips):
            bags = getattr(strip, "channelbags", None)
            cleared = False
            if bags is not None:
                for bag in list(bags):
                    for fc in list(bag.fcurves):
                        bag.fcurves.remove(fc)
                        removed += 1
                        cleared = True
            if not cleared:
                try:
                    layer.strips.remove(strip)
                except Exception:
                    pass
    return removed


def ensure_action_slot(anim_data, action, idblock) -> None:
    """Make sure ``anim_data.action_slot`` targets a slot usable by ``idblock``.

    ``keyframe_insert`` on Blender 5.x requires an action slot compatible with
    the animated ID. Assigning ``anim_data.action`` auto-selects a slot in most
    cases; this covers the remaining ones (e.g. reused/foreign actions).
    """
    if not hasattr(action, "slots"):
        return  # pre-slotted-actions Blender
    try:
        if getattr(anim_data, "action_slot", None) is not None:
            return
        idtype = getattr(idblock, "id_type", "OBJECT") or "OBJECT"
        slot = None
        for s in action.slots:
            if getattr(s, "target_idtype", idtype) == idtype:
                slot = s
                break
        if slot is None:
            try:
                slot = action.slots.new(idtype, getattr(idblock, "name", "BodyMocap"))
            except TypeError:
                slot = action.slots.new(str(idtype), getattr(idblock, "name", "BodyMocap"))
        anim_data.action_slot = slot
    except Exception:
        pass


def action_frame_range(action) -> Tuple[int, int]:
    """Keyframe frame range of an action; (1, 0) when empty."""
    try:
        fr = action.frame_range
        return int(fr[0]), int(fr[1])
    except Exception:
        return 1, 0


# --------------------------------------------------------------------------
# Dependency checks
# --------------------------------------------------------------------------

def add_user_dependency_path() -> None:
    """Discover dependencies installed in Blender's per-user BodyMocap folder."""
    import sys
    from pathlib import Path

    try:
        import bpy
    except ImportError:
        return
    path = Path(bpy.utils.user_resource("DATAFILES")) / "bodymocap" / "site-packages"
    if path.is_dir() and str(path) not in sys.path:
        sys.path.append(str(path))


def check_opencv() -> Tuple[bool, str]:
    try:
        import cv2

        return True, getattr(cv2, "__version__", "unknown")
    except ImportError:
        return False, "not installed"


def _mediapipe_api_flavor() -> Optional[str]:
    """'legacy' | 'tasks' | None — which MediaPipe pose API is usable."""
    try:
        import mediapipe as mp
    except ImportError:
        return None
    try:
        if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
            return "legacy"
    except Exception:
        pass
    try:
        from mediapipe.tasks.python import vision  # noqa: F401

        if hasattr(vision, "PoseLandmarker"):
            return "tasks"
    except Exception:
        pass
    return None


def check_mediapipe() -> Tuple[bool, str]:
    try:
        import mediapipe as mp

        ver = getattr(mp, "__version__", "unknown")
    except ImportError:
        return False, "not installed"
    flavor = _mediapipe_api_flavor()
    if flavor == "legacy":
        return True, f"{ver} (solutions API)"
    if flavor == "tasks":
        return True, f"{ver} (tasks API)"
    return False, f"{ver} (no usable pose API)"


def check_numpy() -> Tuple[bool, str]:
    try:
        import numpy as np

        return True, getattr(np, "__version__", "unknown")
    except ImportError:
        return False, "not installed"


def dependency_status() -> Dict[str, Dict[str, str]]:
    status: Dict[str, Dict[str, str]] = {}
    for name, fn in (
        ("numpy", check_numpy),
        ("opencv", check_opencv),
        ("mediapipe", check_mediapipe),
    ):
        ok, ver = fn()
        status[name] = {
            "available": "yes" if ok else "no",
            "version": ver,
        }
    # Pose model file (only relevant for mediapipe tasks API)
    if _mediapipe_api_flavor() == "tasks":
        try:
            from ..pose.mediapipe_backend import resolve_pose_model_path

            model = resolve_pose_model_path(download=False)
            status["pose model"] = {
                "available": "yes" if model else "no",
                "version": model or "not found",
            }
        except Exception:
            pass
    return status


def dependency_panel_text() -> str:
    st = dependency_status()
    lines = []
    for name, info in st.items():
        mark = "OK" if info["available"] == "yes" else "MISSING"
        lines.append(f"{name}: {mark} ({info['version']})")
    return " | ".join(lines)


def install_deps_instructions() -> str:
    return (
        "Install into Blender's Python, e.g.:\n"
        "  blender --python-expr \"import ensurepip; ensurepip.bootstrap()\"\n"
        "  /path/to/blender/python/bin/python -m pip install "
        "opencv-python-headless mediapipe numpy\n"
        "MediaPipe 1.x also needs a pose_landmarker .task model — BodyMocap "
        "ships one in bodymocap/assets/ and can auto-download it.\n"
        "See INSTALL.md for details. Mock/offline backend works without these."
    )

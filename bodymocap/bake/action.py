"""Bake recording session to Blender Action (FR-060–061, FR-063)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..core.types import Quat, RecordingFrame


def bake_session_to_action(
    frames: List[RecordingFrame],
    armature_obj,
    action_name: str = "BodyMocapAction",
    start_frame: int = 1,
    overwrite: bool = True,
    rotation_mode: str = "QUATERNION",
) -> Tuple[bool, str, Optional[object]]:
    """Insert keyframes for each bone rotation into an Action.

    Returns (ok, message, action_or_None).
    """
    try:
        import bpy
        from mathutils import Quaternion, Euler
    except ImportError:
        return False, "bpy not available (run inside Blender)", None

    if not frames:
        return False, "No frames to bake", None

    from ..utils.blender_compat import clear_action_fcurves, ensure_action_slot

    if overwrite and action_name in bpy.data.actions:
        action = bpy.data.actions[action_name]
        clear_action_fcurves(action)
    else:
        # Ensure unique name if not overwriting
        name = action_name
        if not overwrite:
            base = action_name
            i = 1
            while name in bpy.data.actions:
                name = f"{base}.{i:03d}"
                i += 1
        action = bpy.data.actions.new(name)

    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()

    # Collect all bone names
    bone_names = set()
    for fr in frames:
        bone_names.update(fr.bone_rotations.keys())

    for bone_name in bone_names:
        pb = armature_obj.pose.bones.get(bone_name)
        if pb is None:
            continue
        if rotation_mode == "QUATERNION":
            pb.rotation_mode = "QUATERNION"
        else:
            pb.rotation_mode = "XYZ"

    # Insert keys by temporarily setting pose and keyframe_insert
    prev_action = armature_obj.animation_data.action
    armature_obj.animation_data.action = action
    ensure_action_slot(armature_obj.animation_data, action, armature_obj)

    for fr in frames:
        fnum = start_frame + fr.frame_index
        for bone_name, q in fr.bone_rotations.items():
            pb = armature_obj.pose.bones.get(bone_name)
            if pb is None:
                continue
            if rotation_mode == "QUATERNION":
                pb.rotation_mode = "QUATERNION"
                pb.rotation_quaternion = Quaternion((q.w, q.x, q.y, q.z))
                pb.keyframe_insert(data_path="rotation_quaternion", frame=fnum)
            else:
                pb.rotation_mode = "XYZ"
                quat = Quaternion((q.w, q.x, q.y, q.z))
                pb.rotation_euler = quat.to_euler("XYZ")
                pb.keyframe_insert(data_path="rotation_euler", frame=fnum)

    armature_obj.animation_data.action = action
    return True, f"Baked {len(frames)} frames into Action '{action.name}'", action


def frames_from_rotation_dicts(
    dicts: List[Dict[str, Quat]],
    tracking_ok: bool = True,
) -> List[RecordingFrame]:
    from ..core.types import TrackingState

    state = TrackingState.OK if tracking_ok else TrackingState.DEGRADED
    return [
        RecordingFrame(frame_index=i, bone_rotations=d, tracking_state=state)
        for i, d in enumerate(dicts)
    ]

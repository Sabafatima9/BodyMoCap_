"""Bake recording session to Blender Action (FR-060–061, FR-063).

``ActionKeyer`` is the single keyframe writer: the offline bake replays a finished
take through it, and the capture loop uses it to key the timeline live while
recording so keyframes appear as they are performed.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..core.types import Quat, RecordingFrame, Vec3


def prepare_action(armature_obj, action_name: str, overwrite: bool = True):
    """Create (or clear) an Action, assign it to the armature and make it keyable."""
    import bpy

    from ..utils.blender_compat import clear_action_fcurves, ensure_action_slot

    if overwrite and action_name in bpy.data.actions:
        action = bpy.data.actions[action_name]
        clear_action_fcurves(action)
    else:
        name = action_name
        if not overwrite:
            i = 1
            while name in bpy.data.actions:
                name = f"{action_name}.{i:03d}"
                i += 1
        action = bpy.data.actions.new(name)

    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()
    armature_obj.animation_data.action = action
    ensure_action_slot(armature_obj.animation_data, action, armature_obj)
    return action


class ActionKeyer:
    """Writes per-frame bone rotations / locations into an armature's active Action."""

    def __init__(self, armature_obj, rotation_mode: str = "QUATERNION"):
        self.armature = armature_obj
        self.rotation_mode = "QUATERNION" if rotation_mode == "QUATERNION" else "XYZ"
        self.keyed_bones: set = set()
        self.frames_written = 0

    def key_frame(
        self,
        frame: int,
        rotations: Dict[str, Quat],
        locations: Optional[Dict[str, Vec3]] = None,
    ) -> int:
        """Insert keys for one scene frame. Returns number of bones keyed."""
        from mathutils import Quaternion, Vector

        pose_bones = self.armature.pose.bones
        count = 0
        for bone_name, q in rotations.items():
            pb = pose_bones.get(bone_name)
            if pb is None:
                continue
            quat = Quaternion((q.w, q.x, q.y, q.z))
            if self.rotation_mode == "QUATERNION":
                pb.rotation_mode = "QUATERNION"
                pb.rotation_quaternion = quat
                pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            else:
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = quat.to_euler("XYZ")
                pb.keyframe_insert(data_path="rotation_euler", frame=frame)
            self.keyed_bones.add(bone_name)
            count += 1
        for bone_name, loc in (locations or {}).items():
            pb = pose_bones.get(bone_name)
            if pb is None:
                continue
            pb.location = Vector((loc.x, loc.y, loc.z))
            pb.keyframe_insert(data_path="location", frame=frame)
            self.keyed_bones.add(bone_name)
        if count:
            self.frames_written += 1
        return count


def bake_session_to_action(
    frames: List[RecordingFrame],
    armature_obj,
    action_name: str = "BodyMocapAction",
    start_frame: int = 1,
    overwrite: bool = True,
    rotation_mode: str = "QUATERNION",
) -> Tuple[bool, str, Optional[object]]:
    """Insert keyframes for each recorded frame into an Action.

    Returns (ok, message, action_or_None).
    """
    try:
        import bpy  # noqa: F401
    except ImportError:
        return False, "bpy not available (run inside Blender)", None

    if not frames:
        return False, "No frames to bake", None

    action = prepare_action(armature_obj, action_name, overwrite)
    keyer = ActionKeyer(armature_obj, rotation_mode)
    first = frames[0].frame_index
    for fr in frames:
        keyer.key_frame(start_frame + (fr.frame_index - first), fr.bone_rotations, fr.bone_locations)

    return (
        True,
        f"Baked {len(frames)} frames ({len(keyer.keyed_bones)} bones) into Action '{action.name}'",
        action,
    )


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

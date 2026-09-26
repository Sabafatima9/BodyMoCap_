"""One-click apply baked Action to armature (FR-062)."""

from __future__ import annotations

from typing import Optional, Tuple


def apply_action_to_armature(
    armature_obj,
    action_name: str,
    mode: str = "action",
    nla_track_name: str = "BodyMocap",
    start_frame: int = 1,
) -> Tuple[bool, str]:
    """Assign Action directly or as NLA strip.

    mode: 'action' | 'nla'
    """
    try:
        import bpy
    except ImportError:
        return False, "bpy not available"

    action = bpy.data.actions.get(action_name)
    if action is None:
        return False, f"Action '{action_name}' not found"

    if armature_obj is None or armature_obj.type != "ARMATURE":
        return False, "Target must be an Armature object"

    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()

    if mode == "nla":
        ad = armature_obj.animation_data
        # Clear active action so NLA plays
        ad.action = None
        track = None
        for t in ad.nla_tracks:
            if t.name == nla_track_name:
                track = t
                break
        if track is None:
            track = ad.nla_tracks.new()
            track.name = nla_track_name
        # Remove existing strips with same action name
        for strip in list(track.strips):
            if strip.name == action.name:
                track.strips.remove(strip)
        strip = track.strips.new(action.name, start_frame, action)
        strip.action = action
        return True, f"Applied Action '{action.name}' as NLA strip on track '{nla_track_name}'"

    armature_obj.animation_data.action = action
    return True, f"Assigned Action '{action.name}' to {armature_obj.name}"

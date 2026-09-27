"""Scene / collection properties for BodyMocap."""

from __future__ import annotations

try:
    import bpy
    from bpy.props import (
        BoolProperty,
        CollectionProperty,
        EnumProperty,
        FloatProperty,
        IntProperty,
        PointerProperty,
        StringProperty,
    )
    from bpy.types import PropertyGroup
except ImportError:
    bpy = None
    PropertyGroup = object  # type: ignore


def _is_armature(self, obj) -> bool:
    return obj is not None and obj.type == "ARMATURE"


class BODYMOCAP_PG_MapEntry(PropertyGroup):
    role: StringProperty(name="Role", default="")
    bone_name: StringProperty(name="Bone", default="")


class BODYMOCAP_PG_Settings(PropertyGroup):
    # Camera
    camera_device_index: IntProperty(name="Camera Device", default=0, min=0, max=16)
    camera_video_path: StringProperty(
        name="Video File",
        description="Optional: open this video file instead of the webcam device (for testing)",
        default="",
        subtype="FILE_PATH",
    )
    camera_active: BoolProperty(name="Camera Active", default=False)
    mirror_preview: BoolProperty(
        name="Mirror",
        description="Flip the camera like a mirror: raise your left hand and the rig raises the hand on your left",
        default=True,
    )
    subject_scale: FloatProperty(name="Subject Scale", default=1.0, min=0.1, max=10.0)
    subject_distance: FloatProperty(
        name="Subject Distance",
        description="Approximate distance from the camera (metres) when calibrating; scales root motion depth",
        default=2.0,
        min=0.3,
        max=20.0,
    )
    show_overlay: BoolProperty(name="Show Overlay", default=True)

    # Viewport display
    show_camera_in_viewport: BoolProperty(
        name="Camera in Viewport",
        description="Show the live camera feed with the tracked skeleton in a corner of the 3D Viewport",
        default=True,
    )
    viewport_camera_size: FloatProperty(
        name="Camera Size",
        description="Width of the camera view as a fraction of the viewport",
        default=0.3,
        min=0.12,
        max=0.7,
        subtype="FACTOR",
    )
    viewport_camera_corner: EnumProperty(
        name="Corner",
        items=[
            ("BOTTOM_LEFT", "Bottom Left", ""),
            ("BOTTOM_RIGHT", "Bottom Right", ""),
            ("TOP_LEFT", "Top Left", ""),
            ("TOP_RIGHT", "Top Right", ""),
        ],
        default="BOTTOM_LEFT",
    )
    show_ghost_skeleton: BoolProperty(
        name="3D Tracked Skeleton",
        description="Draw the tracked body as a 3D stick figure in the viewport, scaled to the rig",
        default=True,
    )
    ghost_offset: FloatProperty(
        name="Skeleton Offset",
        description="Sideways offset of the tracked skeleton from the rig (0 draws it on top of the rig)",
        default=0.0,
        min=-10.0,
        max=10.0,
        subtype="DISTANCE",
    )

    # Pose / tracking
    pose_backend: EnumProperty(
        name="Backend",
        items=[
            ("MEDIAPIPE", "MediaPipe", "On-device MediaPipe Pose"),
            ("MOCK", "Mock / Offline", "Synthetic or fixture landmarks"),
        ],
        default="MOCK",
    )
    mock_mode: EnumProperty(
        name="Mock Mode",
        items=[
            ("walk", "Walk", "Synthetic walk cycle"),
            ("idle", "Idle", "Standing idle"),
            ("fixture", "Fixture", "JSON fixture sequence"),
        ],
        default="walk",
    )
    fixture_path: StringProperty(name="Fixture Path", default="", subtype="FILE_PATH")
    min_confidence: FloatProperty(name="Min Confidence", default=0.5, min=0.0, max=1.0)
    lost_policy: EnumProperty(
        name="Lost Policy",
        items=[
            ("hold_last", "Hold Last", "Keep last valid pose"),
            ("interpolate", "Interpolate", "Brief hold then drop"),
            ("drop", "Drop", "Do not apply invalid frames"),
        ],
        default="hold_last",
    )
    smoothing: FloatProperty(
        name="Smoothing",
        description="Temporal smoothing of landmarks (0 = raw, higher = steadier but laggier)",
        default=0.35,
        min=0.0,
        max=0.9,
        subtype="FACTOR",
    )
    tracking_status: StringProperty(name="Tracking", default="Lost")
    capture_fps: FloatProperty(name="Capture FPS", default=0.0)

    # Calibration
    rest_pose_style: EnumProperty(
        name="Rest Pose",
        items=[
            ("T_POSE", "T-Pose", "Arms horizontal"),
            ("A_POSE", "A-Pose", "Arms slightly down"),
        ],
        default="T_POSE",
    )
    calibration_seconds: FloatProperty(name="Calibration Duration", default=2.0, min=0.5, max=10.0)
    is_calibrated: BoolProperty(name="Calibrated", default=False)

    # Mapping
    capture_armature: PointerProperty(
        name="Armature",
        description="Rig driven by the camera (defaults to the active armature when capture starts)",
        type=bpy.types.Object if bpy else None,
        poll=_is_armature,
    )
    mapping_entries: CollectionProperty(type=BODYMOCAP_PG_MapEntry)
    mapping_index: IntProperty(name="Mapping Index", default=0)
    preset_path: StringProperty(name="Preset Path", default="", subtype="FILE_PATH")
    mapping_quality: StringProperty(name="Mapping Quality", default="")
    root_motion: BoolProperty(
        name="Root Motion",
        description="Move the hips bone when you walk around, crouch or step toward/away from the camera",
        default=True,
    )
    root_motion_scale: FloatProperty(
        name="Root Motion Scale",
        default=1.0,
        min=0.0,
        max=5.0,
    )

    # Recording
    is_recording: BoolProperty(name="Recording", default=False)
    is_paused: BoolProperty(name="Paused", default=False)
    record_frame_count: IntProperty(name="Recorded Frames", default=0)
    degraded_warn_fraction: FloatProperty(
        name="Degraded Warn Fraction", default=0.15, min=0.0, max=1.0
    )
    live_keyframes: BoolProperty(
        name="Keyframe Live",
        description="Insert keyframes into the Action while recording so they appear on the timeline as you move",
        default=True,
    )
    follow_playhead: BoolProperty(
        name="Follow Playhead",
        description="Advance the scene frame while recording",
        default=True,
    )
    auto_apply_on_stop: BoolProperty(
        name="Apply on Stop",
        description="When recording stops: bake (if needed), assign the Action and set the scene frame range to the take",
        default=True,
    )
    stop_camera_on_stop: BoolProperty(
        name="Stop Camera with Recording",
        default=False,
    )

    # Bake / apply
    action_name: StringProperty(name="Action Name", default="BodyMocapAction")
    bake_start_frame: IntProperty(name="Start Frame", default=1, min=0)
    overwrite_action: BoolProperty(name="Overwrite Action", default=True)
    apply_mode: EnumProperty(
        name="Apply Mode",
        items=[
            ("action", "Assign Action", "Set as active action"),
            ("nla", "NLA Strip", "Push to NLA track"),
        ],
        default="action",
    )
    rotation_mode: EnumProperty(
        name="Rotation Mode",
        items=[
            ("QUATERNION", "Quaternion", ""),
            ("EULER", "Euler XYZ", ""),
        ],
        default="QUATERNION",
    )

    # Retarget
    source_armature: PointerProperty(
        name="Source",
        description="Armature that has the animation (defaults to the capture rig)",
        type=bpy.types.Object if bpy else None,
        poll=_is_armature,
    )
    target_armature: PointerProperty(
        name="Target",
        description="Armature that should receive the animation",
        type=bpy.types.Object if bpy else None,
        poll=_is_armature,
    )
    retarget_action: PointerProperty(
        name="Action",
        description="Action to transfer (defaults to the source's active Action)",
        type=bpy.types.Action if bpy else None,
    )
    retarget_new_action: StringProperty(
        name="New Action Name",
        description="Leave empty for '<action>_<target>'",
        default="",
    )
    retarget_status: StringProperty(name="Retarget Status", default="")

    # Privacy / debug
    save_debug_video: BoolProperty(
        name="Save Debug Video",
        description="Persist raw video only when explicitly enabled (FR-092)",
        default=False,
    )
    deps_status: StringProperty(name="Deps Status", default="")
    live_apply: BoolProperty(
        name="Live Apply Pose",
        description="Drive the armature while camera/mock is running",
        default=True,
    )
    last_message: StringProperty(name="Last Message", default="")


CLASSES = (BODYMOCAP_PG_MapEntry, BODYMOCAP_PG_Settings)


def register():
    if bpy is None:
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bodymocap = PointerProperty(type=BODYMOCAP_PG_Settings)


def unregister():
    if bpy is None:
        return
    if hasattr(bpy.types.Scene, "bodymocap"):
        del bpy.types.Scene.bodymocap
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

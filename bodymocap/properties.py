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
    mirror_preview: BoolProperty(name="Mirror", default=True)
    subject_scale: FloatProperty(name="Subject Scale", default=1.0, min=0.1, max=10.0)
    subject_distance: FloatProperty(name="Subject Distance", default=2.0, min=0.3, max=20.0)
    show_overlay: BoolProperty(name="Show Overlay", default=True)

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
    tracking_status: StringProperty(name="Tracking", default="Lost")

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
    mapping_entries: CollectionProperty(type=BODYMOCAP_PG_MapEntry)
    mapping_index: IntProperty(name="Mapping Index", default=0)
    preset_path: StringProperty(name="Preset Path", default="", subtype="FILE_PATH")
    mapping_quality: StringProperty(name="Mapping Quality", default="")

    # Recording
    is_recording: BoolProperty(name="Recording", default=False)
    is_paused: BoolProperty(name="Paused", default=False)
    record_frame_count: IntProperty(name="Recorded Frames", default=0)
    degraded_warn_fraction: FloatProperty(
        name="Degraded Warn Fraction", default=0.15, min=0.0, max=1.0
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
    source_armature: StringProperty(name="Source Armature", default="")
    target_armature: StringProperty(name="Target Armature", default="")
    retarget_action: StringProperty(name="Source Action", default="")
    retarget_new_action: StringProperty(name="New Action Name", default="RetargetedAction")

    # Privacy / debug
    save_debug_video: BoolProperty(
        name="Save Debug Video",
        description="Persist raw video only when explicitly enabled (FR-092)",
        default=False,
    )
    deps_status: StringProperty(name="Deps Status", default="")
    live_apply: BoolProperty(
        name="Live Apply Pose",
        description="Drive selected armature while camera/mock is running",
        default=True,
    )


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

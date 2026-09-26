"""Add-on preferences."""

from __future__ import annotations

try:
    import bpy
    from bpy.props import FloatProperty, IntProperty, StringProperty
    from bpy.types import AddonPreferences
except ImportError:
    bpy = None
    AddonPreferences = object  # type: ignore


class BODYMOCAP_AP_Preferences(AddonPreferences):
    # Must equal the installed add-on package name (bodymocap / BodyMocap).
    bl_idname = __package__ or "bodymocap"

    default_device_index: IntProperty(
        name="Default Camera Index",
        default=0,
        min=0,
        max=16,
    )
    log_level: StringProperty(
        name="Log Level",
        default="INFO",
    )
    calibration_seconds: FloatProperty(
        name="Default Calibration Seconds",
        default=2.0,
        min=0.5,
        max=10.0,
    )
    pose_model_path: StringProperty(
        name="Pose Model Path",
        description=(
            "Optional .task model for MediaPipe Tasks API. "
            "Leave empty to use the bundled pose_landmarker_full.task"
        ),
        default="",
        subtype="FILE_PATH",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "default_device_index")
        layout.prop(self, "calibration_seconds")
        layout.prop(self, "log_level")
        layout.prop(self, "pose_model_path")
        from .utils.blender_compat import dependency_panel_text, install_deps_instructions

        layout.separator()
        layout.label(text="Dependencies:")
        layout.label(text=dependency_panel_text())
        box = layout.box()
        for line in install_deps_instructions().split("\n"):
            box.label(text=line)


CLASSES = (BODYMOCAP_AP_Preferences,)


def register():
    if bpy is None:
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    if bpy is None:
        return
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

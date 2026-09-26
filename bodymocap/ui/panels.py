"""N-panel UI for BodyMocap."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Panel
except ImportError:
    bpy = None
    Panel = object  # type: ignore


class BODYMOCAP_PT_main(Panel):
    bl_label = "BodyMocap"
    bl_idname = "BODYMOCAP_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap

        # Dependencies
        box = layout.box()
        box.label(text="Dependencies", icon="INFO")
        if settings.deps_status:
            box.label(text=settings.deps_status)
        else:
            box.label(text="Click Refresh to check")
        row = box.row(align=True)
        row.operator("bodymocap.refresh_deps", text="Refresh")
        row.operator("bodymocap.show_install_help", text="Install Help")

        # Backend / camera
        box = layout.box()
        box.label(text="Capture", icon="CAMERA_DATA")
        box.prop(settings, "pose_backend")
        if settings.pose_backend == "MOCK":
            box.prop(settings, "mock_mode")
            if settings.mock_mode == "fixture":
                box.prop(settings, "fixture_path")
        else:
            box.prop(settings, "camera_device_index")
            box.prop(settings, "camera_video_path")
        box.prop(settings, "mirror_preview")
        box.prop(settings, "show_overlay")
        box.prop(settings, "live_apply")
        row = box.row(align=True)
        if settings.camera_active:
            row.operator("bodymocap.camera_stop", text="Stop", icon="PAUSE")
        else:
            row.operator("bodymocap.camera_start", text="Start", icon="PLAY")
        box.label(text=f"Tracking: {settings.tracking_status}")


class BODYMOCAP_PT_calibration(Panel):
    bl_label = "Calibration"
    bl_idname = "BODYMOCAP_PT_calibration"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        layout.prop(settings, "rest_pose_style")
        layout.prop(settings, "calibration_seconds")
        layout.prop(settings, "subject_scale")
        layout.prop(settings, "subject_distance")
        layout.operator("bodymocap.calibrate", icon="ARMATURE_DATA")
        layout.label(text="Calibrated" if settings.is_calibrated else "Not calibrated")


class BODYMOCAP_PT_tracking(Panel):
    bl_label = "Tracking"
    bl_idname = "BODYMOCAP_PT_tracking"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        layout.prop(settings, "min_confidence")
        layout.prop(settings, "lost_policy")
        layout.prop(settings, "save_debug_video")


class BODYMOCAP_PT_mapping(Panel):
    bl_label = "Bone Mapping"
    bl_idname = "BODYMOCAP_PT_mapping"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        row = layout.row(align=True)
        row.operator("bodymocap.auto_map", icon="AUTO")
        row.operator("bodymocap.mapping_quality", text="Quality")
        row = layout.row()
        row.template_list(
            "BODYMOCAP_UL_mapping",
            "",
            settings,
            "mapping_entries",
            settings,
            "mapping_index",
            rows=6,
        )
        col = row.column(align=True)
        col.operator("bodymocap.mapping_add", icon="ADD", text="")
        col.operator("bodymocap.mapping_remove", icon="REMOVE", text="")
        col.operator("bodymocap.mapping_clear", icon="X", text="")
        if settings.mapping_quality:
            layout.label(text=settings.mapping_quality)
        row = layout.row(align=True)
        row.operator("bodymocap.preset_save", text="Save Preset")
        row.operator("bodymocap.preset_load", text="Load Preset")


class BODYMOCAP_PT_recording(Panel):
    bl_label = "Recording"
    bl_idname = "BODYMOCAP_PT_recording"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        row = layout.row(align=True)
        row.operator("bodymocap.record_start", text="Rec", icon="REC")
        row.operator("bodymocap.record_pause", text="Pause")
        row.operator("bodymocap.record_stop", text="Stop")
        layout.operator("bodymocap.record_discard", text="Discard Take")
        layout.label(text=f"Frames: {settings.record_frame_count}")
        layout.prop(settings, "degraded_warn_fraction")


class BODYMOCAP_PT_bake(Panel):
    bl_label = "Bake / Apply"
    bl_idname = "BODYMOCAP_PT_bake"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        layout.prop(settings, "action_name")
        layout.prop(settings, "bake_start_frame")
        layout.prop(settings, "overwrite_action")
        layout.prop(settings, "rotation_mode")
        layout.operator("bodymocap.bake_action", icon="ACTION")
        layout.prop(settings, "apply_mode")
        layout.operator("bodymocap.apply_action", icon="PLAY")


class BODYMOCAP_PT_retarget(Panel):
    bl_label = "Retarget"
    bl_idname = "BODYMOCAP_PT_retarget"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        layout.prop(settings, "source_armature")
        layout.prop(settings, "target_armature")
        layout.prop(settings, "retarget_action")
        layout.prop(settings, "retarget_new_action")
        layout.operator("bodymocap.detect_chains")
        layout.operator("bodymocap.retarget_transfer", icon="ARROW_LEFTRIGHT")


CLASSES = (
    BODYMOCAP_PT_main,
    BODYMOCAP_PT_calibration,
    BODYMOCAP_PT_tracking,
    BODYMOCAP_PT_mapping,
    BODYMOCAP_PT_recording,
    BODYMOCAP_PT_bake,
    BODYMOCAP_PT_retarget,
)


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

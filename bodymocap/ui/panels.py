"""N-panel UI for BodyMocap.

The main panel is built around two one-click actions — **Record** (camera +
mapping + countdown + keyframes on the timeline) and **Retarget** (source rig →
target rig) — with a "next step" hint that tells the user what to do. Everything
else lives in collapsible sub-panels.
"""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Panel
except ImportError:
    bpy = None
    Panel = object  # type: ignore


def _capture_armature(context, settings):
    from ..operators.camera_ops import get_capture_armature

    return get_capture_armature(context, settings)


def _has_mapping(settings) -> bool:
    return any(e.role and e.bone_name for e in settings.mapping_entries)


def _pending_countdown() -> bool:
    from ..operators.camera_ops import get_live

    return get_live().pending_record_at is not None


def _wrap(text: str, width: int) -> list:
    """Word-wrap for narrow sidebar labels."""
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines[:4]


def next_step(context, settings) -> tuple:
    """(lines, icon) describing what the user should do next (short lines: the sidebar is narrow)."""
    arm = _capture_armature(context, settings)
    if arm is None:
        return ("Step 1: select the armature", "you want to animate"), "OUTLINER_OB_ARMATURE"
    if settings.is_recording:
        if settings.is_paused:
            return ("Paused: Resume or Stop",), "PAUSE"
        return (f"Recording: {settings.record_frame_count} frames", "Perform, then press Stop"), "REC"
    if _pending_countdown():
        from ..operators.camera_ops import get_live

        return (get_live().loop_message or "Get ready...",), "TIME"
    if not settings.camera_active:
        if settings.record_frame_count > 0 and bpy.data.actions.get(settings.action_name):
            return ("Take is on the timeline", "Space to play, or Retarget it"), "PLAY"
        return ("Step 2: press Record", "(or Start Camera to preview)"), "REC"
    if not _has_mapping(settings):
        return ("Click Auto-Map so the", "landmarks drive your bones"), "AUTO"
    if settings.tracking_status not in ("OK", "DEGRADED"):
        return ("Step back: whole body", "should be in the camera view"), "CAMERA_DATA"
    if not settings.is_calibrated:
        return ("Optional: T-pose + Calibrate", "then press Record"), "ARMATURE_DATA"
    return ("Press Record: countdown,", "then move!"), "REC"


class BODYMOCAP_PT_main(Panel):
    bl_label = "BodyMocap"
    bl_idname = "BODYMOCAP_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        arm = _capture_armature(context, settings)

        lines, icon = next_step(context, settings)
        hint = layout.box()
        col = hint.column(align=True)
        col.scale_y = 0.85
        for i, line in enumerate(lines):
            col.label(text=line, icon=icon if i == 0 else "BLANK1")
        if not settings.is_recording and not _pending_countdown():
            from ..operators.camera_ops import get_live

            loop_message = get_live().loop_message if settings.camera_active else ""
            for chunk in _wrap(loop_message or settings.last_message, 42):
                col.label(text=chunk, icon="BLANK1")

        col = layout.column(align=True)
        col.prop(settings, "capture_armature", text="Rig", icon="ARMATURE_DATA")

        # --- One-click record -------------------------------------------------
        row = col.row(align=True)
        row.scale_y = 1.8
        recording = settings.is_recording or _pending_countdown()
        if recording:
            row.operator("bodymocap.quick_record", text="Stop & Apply", icon="SNAP_FACE", depress=True)
            row.operator(
                "bodymocap.record_pause",
                text="",
                icon="PLAY" if settings.is_paused else "PAUSE",
            )
        else:
            row.operator("bodymocap.quick_record", text="Record", icon="REC")

        row = col.row(align=True)
        if settings.camera_active:
            row.operator("bodymocap.camera_stop", text="Stop Camera", icon="CANCEL")
        else:
            row.operator("bodymocap.camera_start", text="Start Camera", icon="CAMERA_DATA")
        row.operator("bodymocap.calibrate", text="Calibrate", icon="ARMATURE_DATA")

        status = layout.row(align=True)
        tracking = settings.tracking_status
        if settings.camera_active:
            tracking = f"{tracking}  {settings.capture_fps:.0f} fps"
        status.label(text=tracking, icon="CHECKMARK" if settings.tracking_status == "OK" else "ERROR")
        status.label(
            text="Calibrated" if settings.is_calibrated else "Not calibrated",
            icon="ARMATURE_DATA" if settings.is_calibrated else "BLANK1",
        )

        # --- One-click retarget -----------------------------------------------
        box = layout.box()
        box.label(text="Retarget to another rig", icon="ARROW_LEFTRIGHT")
        row = box.row(align=True)
        row.prop(settings, "source_armature", text="From")
        row.operator("bodymocap.retarget_swap", text="", icon="FILE_REFRESH")
        row.prop(settings, "target_armature", text="To")
        box.prop(settings, "retarget_action", text="Action")
        big = box.row()
        big.scale_y = 1.5
        big.operator("bodymocap.retarget", text="Retarget Animation", icon="ARROW_LEFTRIGHT")
        if settings.retarget_status:
            col = box.column(align=True)
            col.scale_y = 0.85
            for i, chunk in enumerate(_wrap(settings.retarget_status, 42)[:3]):
                col.label(text=chunk, icon="INFO" if i == 0 else "BLANK1")
        elif settings.source_armature is None and settings.target_armature is None:
            col = box.column(align=True)
            col.scale_y = 0.85
            col.label(text="Tip: pick From/To above, or select", icon="QUESTION")
            col.label(text="target then ctrl-click source", icon="BLANK1")


class BODYMOCAP_PT_capture(Panel):
    bl_label = "Camera & Display"
    bl_idname = "BODYMOCAP_PT_capture"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap

        box = layout.box()
        box.label(text="Source", icon="CAMERA_DATA")
        box.prop(settings, "pose_backend")
        if settings.pose_backend == "MOCK":
            box.prop(settings, "mock_mode")
            if settings.mock_mode == "fixture":
                box.prop(settings, "fixture_path")
        else:
            box.prop(settings, "camera_device_index")
            box.prop(settings, "camera_video_path")
        box.prop(settings, "mirror_preview")

        box = layout.box()
        box.label(text="Viewport", icon="RESTRICT_VIEW_OFF")
        box.prop(settings, "show_camera_in_viewport")
        sub = box.column(align=True)
        sub.active = settings.show_camera_in_viewport
        sub.prop(settings, "viewport_camera_size")
        sub.prop(settings, "viewport_camera_corner", text="")
        box.prop(settings, "show_overlay", text="Skeleton on Camera")
        box.prop(settings, "show_ghost_skeleton")
        sub = box.column(align=True)
        sub.active = settings.show_ghost_skeleton
        sub.prop(settings, "ghost_offset")
        box.prop(settings, "live_apply")

        box = layout.box()
        box.label(text="Dependencies", icon="INFO")
        if settings.deps_status:
            box.label(text=settings.deps_status)
        else:
            box.label(text="Click Refresh to check")
        row = box.row(align=True)
        row.operator("bodymocap.refresh_deps", text="Refresh")
        row.operator("bodymocap.show_install_help", text="Install Help")


class BODYMOCAP_PT_calibration(Panel):
    bl_label = "Calibration & 3D Motion"
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
        layout.prop(settings, "subject_distance")
        layout.prop(settings, "subject_scale")
        row = layout.row(align=True)
        row.operator("bodymocap.calibrate", icon="ARMATURE_DATA")
        row.operator("bodymocap.reset_calibration", text="", icon="X")
        layout.label(text="Calibrated" if settings.is_calibrated else "Not calibrated")
        layout.separator()
        layout.prop(settings, "root_motion")
        sub = layout.column(align=True)
        sub.active = settings.root_motion
        sub.prop(settings, "root_motion_scale")


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
        layout.prop(settings, "smoothing")
        layout.prop(settings, "lost_policy")
        layout.prop(settings, "save_debug_video")


class BODYMOCAP_PT_mapping(Panel):
    bl_label = "Bone Mapping"
    bl_idname = "BODYMOCAP_PT_mapping"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

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
    bl_label = "Recording & Timeline"
    bl_idname = "BODYMOCAP_PT_recording"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        row = layout.row(align=True)
        row.operator("bodymocap.record_start", text="Rec", icon="REC")
        row.operator("bodymocap.record_pause", text="Pause")
        row.operator("bodymocap.record_stop", text="Stop")
        layout.operator("bodymocap.record_discard", text="Discard Take")
        layout.label(text=f"Frames: {settings.record_frame_count}   Scene FPS: {context.scene.render.fps}")
        layout.separator()
        layout.prop(settings, "live_keyframes")
        sub = layout.column(align=True)
        sub.active = settings.live_keyframes
        sub.prop(settings, "follow_playhead")
        layout.prop(settings, "auto_apply_on_stop")
        layout.prop(settings, "stop_camera_on_stop")
        layout.prop(settings, "degraded_warn_fraction")


class BODYMOCAP_PT_bake(Panel):
    bl_label = "Action / Bake"
    bl_idname = "BODYMOCAP_PT_bake"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

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
    bl_label = "Retarget Details"
    bl_idname = "BODYMOCAP_PT_retarget"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BodyMocap"
    bl_parent_id = "BODYMOCAP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bodymocap
        layout.prop(settings, "retarget_new_action")
        layout.operator("bodymocap.detect_chains")
        if settings.retarget_status:
            col = layout.column(align=True)
            text = settings.retarget_status
            while text:
                col.label(text=text[:60])
                text = text[60:]


CLASSES = (
    BODYMOCAP_PT_main,
    BODYMOCAP_PT_capture,
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

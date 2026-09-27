"""Bake and apply operators (FR-060–063)."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore


class BODYMOCAP_OT_bake_action(Operator):
    bl_idname = "bodymocap.bake_action"
    bl_label = "Bake to Action"
    bl_description = "Bake the recorded take into a Blender Action on the capture armature"

    def execute(self, context):
        from ..bake.action import bake_session_to_action
        from ..recording.session import get_active_session
        from .camera_ops import get_capture_armature

        settings = context.scene.bodymocap
        arm = get_capture_armature(context, settings)
        if arm is None:
            self.report({"ERROR"}, "Select an Armature object")
            return {"CANCELLED"}

        session = get_active_session()
        if session.frame_count() == 0:
            self.report({"ERROR"}, "No recorded frames to bake")
            return {"CANCELLED"}

        if session.should_warn_tracking():
            self.report({"WARNING"}, session.tracking_warning_message())

        ok, msg, action = bake_session_to_action(
            session.frames,
            arm,
            action_name=settings.action_name,
            start_frame=settings.bake_start_frame,
            overwrite=settings.overwrite_action,
            rotation_mode=settings.rotation_mode,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        if action:
            settings.action_name = action.name
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class BODYMOCAP_OT_apply_action(Operator):
    bl_idname = "bodymocap.apply_action"
    bl_label = "Apply Action"
    bl_description = "One-click assign baked Action (or NLA strip) to the capture armature"

    def execute(self, context):
        from ..bake.apply import apply_action_to_armature
        from .camera_ops import get_capture_armature

        settings = context.scene.bodymocap
        arm = get_capture_armature(context, settings)
        if arm is None:
            self.report({"ERROR"}, "Select an Armature object")
            return {"CANCELLED"}

        ok, msg = apply_action_to_armature(
            arm,
            settings.action_name,
            mode=settings.apply_mode,
            start_frame=settings.bake_start_frame,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        action = bpy.data.actions.get(settings.action_name)
        if action is not None:
            start, end = int(action.frame_range[0]), int(action.frame_range[1])
            if end > start:
                context.scene.frame_start = start
                context.scene.frame_end = end
                context.scene.frame_set(start)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


CLASSES = (
    BODYMOCAP_OT_bake_action,
    BODYMOCAP_OT_apply_action,
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

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
    bl_description = "Bake recorded take into a Blender Action"

    def execute(self, context):
        from ..bake.action import bake_session_to_action
        from ..recording.session import get_active_session

        arm = context.active_object
        if arm is None or arm.type != "ARMATURE":
            self.report({"ERROR"}, "Select an Armature object")
            return {"CANCELLED"}

        settings = context.scene.bodymocap
        session = get_active_session()
        if session.frame_count() == 0:
            self.report({"ERROR"}, "No recorded frames to bake")
            return {"CANCELLED"}

        if session.should_warn_tracking():
            self.report({"WARNING"}, session.tracking_warning_message())

        rot_mode = "QUATERNION" if settings.rotation_mode == "QUATERNION" else "EULER"
        ok, msg, action = bake_session_to_action(
            session.frames,
            arm,
            action_name=settings.action_name,
            start_frame=settings.bake_start_frame,
            overwrite=settings.overwrite_action,
            rotation_mode=rot_mode,
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
    bl_description = "One-click assign baked Action (or NLA strip) to armature"

    def execute(self, context):
        from ..bake.apply import apply_action_to_armature

        arm = context.active_object
        if arm is None or arm.type != "ARMATURE":
            self.report({"ERROR"}, "Select an Armature object")
            return {"CANCELLED"}

        settings = context.scene.bodymocap
        ok, msg = apply_action_to_armature(
            arm,
            settings.action_name,
            mode=settings.apply_mode,
            start_frame=settings.bake_start_frame,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
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

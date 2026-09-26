"""Cross-armature retarget operators (FR-070–076)."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore


class BODYMOCAP_OT_detect_chains(Operator):
    bl_idname = "bodymocap.detect_chains"
    bl_label = "Detect Bone Chains"
    bl_description = "Detect humanoid chains on source/target armatures"

    def execute(self, context):
        from ..retarget.chains import detect_chains

        settings = context.scene.bodymocap
        messages = []
        for label, name in (("Source", settings.source_armature), ("Target", settings.target_armature)):
            obj = bpy.data.objects.get(name) if name else None
            if obj is None and label == "Source":
                obj = context.active_object
            if obj is None or obj.type != "ARMATURE":
                messages.append(f"{label}: no armature")
                continue
            chains = detect_chains([b.name for b in obj.data.bones])
            parts = [f"{k}({len(v.bone_names)})" for k, v in chains.items()]
            messages.append(f"{label} {obj.name}: " + (", ".join(parts) if parts else "none"))
        for m in messages:
            self.report({"INFO"}, m)
        return {"FINISHED"}


class BODYMOCAP_OT_retarget_transfer(Operator):
    bl_idname = "bodymocap.retarget_transfer"
    bl_label = "Retarget Action"
    bl_description = "Transfer source Action to target armature with N:M chain remap"

    def execute(self, context):
        from ..retarget.transfer import transfer_in_blender

        settings = context.scene.bodymocap
        src_name = settings.source_armature
        tgt_name = settings.target_armature
        if not src_name:
            arm = context.active_object
            if arm and arm.type == "ARMATURE":
                src_name = arm.name
        if not tgt_name:
            self.report({"ERROR"}, "Set Target Armature name in the panel")
            return {"CANCELLED"}
        if not src_name:
            self.report({"ERROR"}, "Set Source Armature or select one")
            return {"CANCELLED"}

        ok, msg = transfer_in_blender(
            src_name,
            tgt_name,
            settings.retarget_action,
            settings.retarget_new_action,
            start_frame=settings.bake_start_frame,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


CLASSES = (
    BODYMOCAP_OT_detect_chains,
    BODYMOCAP_OT_retarget_transfer,
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

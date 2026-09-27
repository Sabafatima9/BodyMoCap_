"""Cross-armature retarget operators (FR-070–076).

``bodymocap.retarget`` is the one-click path: it works out the source rig, the
target rig and the Action from the pickers (falling back to the capture rig, the
selection and the source's active Action), transfers, assigns the result to the
target and frames the timeline on it.
"""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore


def resolve_retarget_pair(context, settings):
    """(source, target) armatures from pickers → capture rig → selection. Either may be None."""
    from .camera_ops import get_capture_armature

    source = settings.source_armature
    target = settings.target_armature
    if source is not None and source.name not in bpy.data.objects:
        source = None
    if target is not None and target.name not in bpy.data.objects:
        target = None

    selected = [o for o in context.selected_objects if o.type == "ARMATURE"]
    active = context.active_object if (context.active_object and context.active_object.type == "ARMATURE") else None

    if source is None:
        source = get_capture_armature(context, settings)
        if source is None or (target is not None and source == target):
            others = [o for o in selected if o != target and o != active]
            source = others[0] if others else (active if active != target else None)
    if target is None:
        if active is not None and active != source:
            target = active
        else:
            others = [o for o in selected if o != source]
            target = others[0] if others else None
    return source, target


def resolve_retarget_action(settings, source):
    action = settings.retarget_action
    if action is not None and action.name in bpy.data.actions:
        return action
    if source is not None and source.animation_data and source.animation_data.action:
        return source.animation_data.action
    return bpy.data.actions.get(settings.action_name)


class BODYMOCAP_OT_detect_chains(Operator):
    bl_idname = "bodymocap.detect_chains"
    bl_label = "Detect Bone Chains"
    bl_description = "Detect humanoid chains on source/target armatures"

    def execute(self, context):
        from ..retarget.chains import detect_chains

        settings = context.scene.bodymocap
        source, target = resolve_retarget_pair(context, settings)
        messages = []
        for label, obj in (("Source", source), ("Target", target)):
            if obj is None or obj.type != "ARMATURE":
                messages.append(f"{label}: no armature")
                continue
            chains = detect_chains([b.name for b in obj.data.bones])
            parts = [f"{k}({len(v.bone_names)})" for k, v in chains.items()]
            messages.append(f"{label} {obj.name}: " + (", ".join(parts) if parts else "none"))
        settings.retarget_status = " | ".join(messages)
        for m in messages:
            self.report({"INFO"}, m)
        return {"FINISHED"}


def run_retarget(operator, context):
    """Shared body of the retarget operators (Blender cannot register Operator subclasses)."""
    from ..retarget.transfer import transfer_in_blender

    settings = context.scene.bodymocap
    source, target = resolve_retarget_pair(context, settings)
    if source is None:
        operator.report({"ERROR"}, "Pick a Source armature (the one that has the animation)")
        return {"CANCELLED"}
    if target is None:
        operator.report({"ERROR"}, "Pick a Target armature (or select it with the source)")
        return {"CANCELLED"}
    if source == target:
        operator.report({"ERROR"}, "Source and Target must be different armatures")
        return {"CANCELLED"}
    action = resolve_retarget_action(settings, source)
    if action is None:
        operator.report({"ERROR"}, f"'{source.name}' has no animation to transfer - record or pick an Action")
        return {"CANCELLED"}

    settings.source_armature = source
    settings.target_armature = target
    new_name = settings.retarget_new_action.strip() or f"{action.name}_{target.name}"

    ok, msg = transfer_in_blender(
        source.name,
        target.name,
        action.name,
        new_name,
        start_frame=int(action.frame_range[0]),
    )
    settings.retarget_status = msg
    if not ok:
        operator.report({"ERROR"}, msg)
        return {"CANCELLED"}

    new_action = bpy.data.actions.get(new_name)
    if new_action is not None:
        start, end = int(new_action.frame_range[0]), int(new_action.frame_range[1])
        if end > start:
            context.scene.frame_start = min(context.scene.frame_start, start)
            context.scene.frame_end = max(context.scene.frame_end, end)
            context.scene.frame_set(start)
    operator.report({"INFO"}, msg)
    return {"FINISHED"}


class BODYMOCAP_OT_retarget(Operator):
    bl_idname = "bodymocap.retarget"
    bl_label = "Retarget"
    bl_description = (
        "One click: transfer the source armature's animation onto the target armature "
        "(different bone counts are remapped per chain) and play it on the target"
    )

    def execute(self, context):
        return run_retarget(self, context)


class BODYMOCAP_OT_retarget_transfer(Operator):
    """Backwards-compatible id for the retarget operator."""

    bl_idname = "bodymocap.retarget_transfer"
    bl_label = "Retarget Action"
    bl_description = BODYMOCAP_OT_retarget.bl_description

    def execute(self, context):
        return run_retarget(self, context)


class BODYMOCAP_OT_retarget_swap(Operator):
    bl_idname = "bodymocap.retarget_swap"
    bl_label = "Swap"
    bl_description = "Swap source and target armatures"

    def execute(self, context):
        settings = context.scene.bodymocap
        settings.source_armature, settings.target_armature = settings.target_armature, settings.source_armature
        return {"FINISHED"}


CLASSES = (
    BODYMOCAP_OT_detect_chains,
    BODYMOCAP_OT_retarget,
    BODYMOCAP_OT_retarget_transfer,
    BODYMOCAP_OT_retarget_swap,
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

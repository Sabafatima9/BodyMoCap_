"""Mapping auto/manual/preset operators (FR-040–045)."""

from __future__ import annotations

try:
    import bpy
    from bpy.props import StringProperty
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore
    StringProperty = lambda **kwargs: None  # type: ignore


def _active_armature(context):
    obj = context.active_object
    if obj and obj.type == "ARMATURE":
        return obj
    return None


def _set_entries(settings, role_to_bone):
    settings.mapping_entries.clear()
    for role, bone in sorted(role_to_bone.items()):
        entry = settings.mapping_entries.add()
        entry.role = role
        entry.bone_name = bone


def _get_entries(settings):
    return {e.role: e.bone_name for e in settings.mapping_entries if e.role}


class BODYMOCAP_OT_auto_map(Operator):
    bl_idname = "bodymocap.auto_map"
    bl_label = "Auto-Map Bones"
    bl_description = "Map humanoid roles to armature bones via name heuristics"

    def execute(self, context):
        from ..mapping.auto_map import build_auto_mapping, evaluate_mapping_quality, mapping_quality_message

        arm = _active_armature(context)
        if arm is None:
            self.report({"ERROR"}, "Select an Armature object")
            return {"CANCELLED"}

        bone_names = [b.name for b in arm.data.bones]
        mapping = build_auto_mapping(bone_names)
        settings = context.scene.bodymocap
        _set_entries(settings, mapping)
        quality = evaluate_mapping_quality(mapping, bone_names)
        settings.mapping_quality = mapping_quality_message(quality)
        level = {"INFO"} if quality.ok or quality.mapped_count > 0 else {"WARNING"}
        self.report(level, settings.mapping_quality)
        return {"FINISHED"}


class BODYMOCAP_OT_mapping_add(Operator):
    bl_idname = "bodymocap.mapping_add"
    bl_label = "Add Mapping Entry"

    def execute(self, context):
        settings = context.scene.bodymocap
        entry = settings.mapping_entries.add()
        entry.role = "spine"
        entry.bone_name = ""
        settings.mapping_index = len(settings.mapping_entries) - 1
        return {"FINISHED"}


class BODYMOCAP_OT_mapping_remove(Operator):
    bl_idname = "bodymocap.mapping_remove"
    bl_label = "Remove Mapping Entry"

    def execute(self, context):
        settings = context.scene.bodymocap
        idx = settings.mapping_index
        if 0 <= idx < len(settings.mapping_entries):
            settings.mapping_entries.remove(idx)
            settings.mapping_index = min(idx, len(settings.mapping_entries) - 1)
        return {"FINISHED"}


class BODYMOCAP_OT_mapping_clear(Operator):
    bl_idname = "bodymocap.mapping_clear"
    bl_label = "Clear Mapping"

    def execute(self, context):
        context.scene.bodymocap.mapping_entries.clear()
        context.scene.bodymocap.mapping_quality = ""
        self.report({"INFO"}, "Mapping cleared")
        return {"FINISHED"}


class BODYMOCAP_OT_mapping_quality(Operator):
    bl_idname = "bodymocap.mapping_quality"
    bl_label = "Check Mapping Quality"

    def execute(self, context):
        from ..mapping.auto_map import evaluate_mapping_quality, mapping_quality_message

        arm = _active_armature(context)
        if arm is None:
            self.report({"ERROR"}, "Select an Armature object")
            return {"CANCELLED"}
        settings = context.scene.bodymocap
        mapping = _get_entries(settings)
        bone_names = [b.name for b in arm.data.bones]
        quality = evaluate_mapping_quality(mapping, bone_names)
        settings.mapping_quality = mapping_quality_message(quality)
        self.report({"INFO"}, settings.mapping_quality)
        return {"FINISHED"}


class BODYMOCAP_OT_preset_save(Operator):
    bl_idname = "bodymocap.preset_save"
    bl_label = "Save Mapping Preset"
    bl_description = "Save current mapping to JSON"

    filepath: StringProperty(subtype="FILE_PATH", default="//bodymocap_mapping.json")

    def invoke(self, context, event):
        settings = context.scene.bodymocap
        if settings.preset_path:
            self.filepath = settings.preset_path
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from ..mapping.presets import save_preset

        settings = context.scene.bodymocap
        mapping = _get_entries(settings)
        if not mapping:
            self.report({"ERROR"}, "No mapping entries to save")
            return {"CANCELLED"}
        path = bpy.path.abspath(self.filepath)
        arm = _active_armature(context)
        meta = {"armature": arm.name if arm else ""}
        try:
            save_preset(path, mapping, meta)
        except Exception as exc:
            self.report({"ERROR"}, f"Save failed: {exc}")
            return {"CANCELLED"}
        settings.preset_path = self.filepath
        self.report({"INFO"}, f"Saved preset: {path}")
        return {"FINISHED"}


class BODYMOCAP_OT_preset_load(Operator):
    bl_idname = "bodymocap.preset_load"
    bl_label = "Load Mapping Preset"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        settings = context.scene.bodymocap
        if settings.preset_path:
            self.filepath = settings.preset_path
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from ..mapping.auto_map import evaluate_mapping_quality, mapping_quality_message
        from ..mapping.presets import load_preset

        path = bpy.path.abspath(self.filepath)
        try:
            mapping = load_preset(path)
        except Exception as exc:
            self.report({"ERROR"}, f"Load failed: {exc}")
            return {"CANCELLED"}
        settings = context.scene.bodymocap
        _set_entries(settings, mapping)
        settings.preset_path = self.filepath
        arm = _active_armature(context)
        if arm:
            quality = evaluate_mapping_quality(mapping, [b.name for b in arm.data.bones])
            settings.mapping_quality = mapping_quality_message(quality)
        self.report({"INFO"}, f"Loaded {len(mapping)} mapping entries")
        return {"FINISHED"}


CLASSES = (
    BODYMOCAP_OT_auto_map,
    BODYMOCAP_OT_mapping_add,
    BODYMOCAP_OT_mapping_remove,
    BODYMOCAP_OT_mapping_clear,
    BODYMOCAP_OT_mapping_quality,
    BODYMOCAP_OT_preset_save,
    BODYMOCAP_OT_preset_load,
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

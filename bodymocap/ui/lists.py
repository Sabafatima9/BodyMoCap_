"""UIList for mapping entries (FR-041)."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import UIList
except ImportError:
    bpy = None
    UIList = object  # type: ignore


class BODYMOCAP_UL_mapping(UIList):
    bl_idname = "BODYMOCAP_UL_mapping"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "role", text="", emboss=False)
        row.prop(item, "bone_name", text="", emboss=True)


CLASSES = (BODYMOCAP_UL_mapping,)


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

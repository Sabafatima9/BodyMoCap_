"""Dependency status / refresh operators (FR-003, FR-082)."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore


class BODYMOCAP_OT_refresh_deps(Operator):
    bl_idname = "bodymocap.refresh_deps"
    bl_label = "Refresh Dependencies"
    bl_description = "Re-check OpenCV / MediaPipe / NumPy availability"

    def execute(self, context):
        from ..utils.blender_compat import dependency_panel_text, install_deps_instructions

        settings = context.scene.bodymocap
        settings.deps_status = dependency_panel_text()
        self.report({"INFO"}, settings.deps_status)
        if "MISSING" in settings.deps_status:
            self.report({"WARNING"}, "Some dependencies missing. See INSTALL.md.")
            for line in install_deps_instructions().split("\n")[:2]:
                self.report({"INFO"}, line)
        return {"FINISHED"}


class BODYMOCAP_OT_show_install_help(Operator):
    bl_idname = "bodymocap.show_install_help"
    bl_label = "Dependency Install Help"

    def execute(self, context):
        from ..utils.blender_compat import install_deps_instructions

        for line in install_deps_instructions().split("\n"):
            if line.strip():
                self.report({"INFO"}, line)
        return {"FINISHED"}


CLASSES = (
    BODYMOCAP_OT_refresh_deps,
    BODYMOCAP_OT_show_install_help,
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

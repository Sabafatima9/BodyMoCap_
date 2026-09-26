"""BodyMocap — camera body mocap + N:M retargeting for Blender 4.x / 5.x."""

bl_info = {
    "name": "BodyMocap",
    "author": "BodyMocap Project",
    "version": (1, 1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > BodyMocap",
    "description": (
        "Webcam body motion capture, joint→bone mapping, Action bake, "
        "and N:M cross-armature retargeting"
    ),
    "category": "Animation",
    "doc_url": "",
    "tracker_url": "",
}

# Guarded imports so missing deps never crash registration (FR-003, FR-082)
_REGISTERED = False


def register():
    global _REGISTERED
    import bpy

    from . import preferences, properties
    from .ui import lists, panels
    from .operators import (
        bake_ops,
        camera_ops,
        deps_ops,
        mapping_ops,
        record_ops,
        retarget_ops,
    )
    from .utils.blender_compat import (
        add_user_dependency_path,
        dependency_panel_text,
        is_supported_blender,
        version_warning_message,
    )
    from .utils.logging_util import log_info, log_warning

    add_user_dependency_path()
    preferences.register()
    properties.register()
    lists.register()
    panels.register()
    deps_ops.register()
    camera_ops.register()
    mapping_ops.register()
    record_ops.register()
    bake_ops.register()
    retarget_ops.register()

    _REGISTERED = True

    if not is_supported_blender((4, 0, 0)):
        log_warning(version_warning_message((4, 0, 0)))
        # Still registered; operators themselves check and report ERROR

    # Seed deps status on scenes when possible
    try:
        for scene in bpy.data.scenes:
            if hasattr(scene, "bodymocap"):
                scene.bodymocap.deps_status = dependency_panel_text()
    except Exception:
        pass

    log_info("BodyMocap registered")


def unregister():
    global _REGISTERED
    from . import preferences, properties
    from .ui import lists, panels
    from .operators import (
        bake_ops,
        camera_ops,
        deps_ops,
        mapping_ops,
        record_ops,
        retarget_ops,
    )
    from .camera.capture import get_capture
    from .overlay.draw import unregister_viewport_draw_handler
    from .utils.logging_util import log_info

    try:
        get_capture().close()
    except Exception:
        pass
    unregister_viewport_draw_handler()

    retarget_ops.unregister()
    bake_ops.unregister()
    record_ops.unregister()
    mapping_ops.unregister()
    camera_ops.unregister()
    deps_ops.unregister()
    panels.unregister()
    lists.unregister()
    properties.unregister()
    preferences.unregister()

    _REGISTERED = False
    log_info("BodyMocap unregistered")


if __name__ == "__main__":
    register()

"""Recording session operators (FR-050–053)."""

from __future__ import annotations

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore


class BODYMOCAP_OT_record_start(Operator):
    bl_idname = "bodymocap.record_start"
    bl_label = "Start Recording"

    def execute(self, context):
        from ..recording.session import get_active_session, reset_active_session

        settings = context.scene.bodymocap
        if not settings.camera_active and settings.pose_backend != "MOCK":
            # Allow recording with mock even if user forgot start — but prefer active loop
            self.report(
                {"WARNING"},
                "Capture not active. Start Camera (Mock OK) for live recording.",
            )
        session = reset_active_session()
        fps = context.scene.render.fps
        session.degraded_warn_fraction = settings.degraded_warn_fraction
        session.start(fps=float(fps))
        settings.is_recording = True
        settings.is_paused = False
        settings.record_frame_count = 0
        self.report({"INFO"}, "Recording started")
        return {"FINISHED"}


class BODYMOCAP_OT_record_pause(Operator):
    bl_idname = "bodymocap.record_pause"
    bl_label = "Pause / Resume Recording"

    def execute(self, context):
        from ..recording.session import get_active_session

        settings = context.scene.bodymocap
        session = get_active_session()
        if not session.is_recording:
            self.report({"ERROR"}, "Not recording")
            return {"CANCELLED"}
        if session.is_paused:
            session.resume()
            settings.is_paused = False
            self.report({"INFO"}, "Recording resumed")
        else:
            session.pause()
            settings.is_paused = True
            self.report({"INFO"}, "Recording paused")
        return {"FINISHED"}


class BODYMOCAP_OT_record_stop(Operator):
    bl_idname = "bodymocap.record_stop"
    bl_label = "Stop Recording"

    def execute(self, context):
        from ..recording.session import get_active_session

        settings = context.scene.bodymocap
        session = get_active_session()
        session.stop()
        settings.is_recording = False
        settings.is_paused = False
        settings.record_frame_count = session.frame_count()
        if session.should_warn_tracking():
            self.report({"WARNING"}, session.tracking_warning_message())
        self.report({"INFO"}, f"Recording stopped — {session.frame_count()} frames")
        return {"FINISHED"}


class BODYMOCAP_OT_record_discard(Operator):
    bl_idname = "bodymocap.record_discard"
    bl_label = "Discard Take"

    def execute(self, context):
        from ..recording.session import get_active_session

        settings = context.scene.bodymocap
        session = get_active_session()
        session.discard()
        settings.is_recording = False
        settings.is_paused = False
        settings.record_frame_count = 0
        self.report({"INFO"}, "Take discarded")
        return {"FINISHED"}


CLASSES = (
    BODYMOCAP_OT_record_start,
    BODYMOCAP_OT_record_pause,
    BODYMOCAP_OT_record_stop,
    BODYMOCAP_OT_record_discard,
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

"""Recording session operators (FR-050–053) and the one-click Record flow.

Recording is driven by the capture loop (``camera_ops``): every solved frame is
stored in the :class:`RecordingSession` and, when *Keyframe Live* is on, keyed
straight into the rig's Action so the timeline fills up while you perform.
Stopping applies the take (assign Action, set the scene range) automatically.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore

_LIVE_KEYER = None
_LIVE_FIRST_INDEX: Optional[int] = None

RECORD_COUNTDOWN_SECONDS = 3.0


def _reset_live_keyer() -> None:
    global _LIVE_KEYER, _LIVE_FIRST_INDEX
    _LIVE_KEYER = None
    _LIVE_FIRST_INDEX = None


def begin_recording(context, settings) -> Tuple[bool, str]:
    """Start a take now (camera loop must be running). Returns (ok, message)."""
    global _LIVE_KEYER, _LIVE_FIRST_INDEX

    from ..recording.session import reset_active_session
    from .camera_ops import get_capture_armature

    arm = get_capture_armature(context, settings)
    if arm is None:
        return False, "Select an armature to record"

    session = reset_active_session()
    session.degraded_warn_fraction = settings.degraded_warn_fraction
    session.start(fps=float(context.scene.render.fps), timestamp=time.time())
    settings.is_recording = True
    settings.is_paused = False
    settings.record_frame_count = 0
    _reset_live_keyer()

    if settings.live_keyframes:
        from ..bake.action import ActionKeyer, prepare_action

        action = prepare_action(arm, settings.action_name, settings.overwrite_action)
        settings.action_name = action.name
        _LIVE_KEYER = ActionKeyer(arm, settings.rotation_mode)
        if settings.follow_playhead:
            context.scene.frame_set(settings.bake_start_frame)

    from ..overlay.viewport import update_overlay

    update_overlay(recording=True, paused=False, record_started=time.time(), frame_count=0)
    settings.last_message = ""
    return True, "Recording"


def key_live_frame(context, settings, arm, frame) -> None:
    """Key one recorded frame into the live Action and move the playhead."""
    global _LIVE_FIRST_INDEX
    if _LIVE_KEYER is None or not settings.live_keyframes:
        return
    if _LIVE_FIRST_INDEX is None:
        _LIVE_FIRST_INDEX = frame.frame_index
    scene_frame = settings.bake_start_frame + (frame.frame_index - _LIVE_FIRST_INDEX)
    _LIVE_KEYER.key_frame(scene_frame, frame.bone_rotations, frame.bone_locations)
    if settings.follow_playhead and context.scene.frame_current != scene_frame:
        # Assigning frame_current tags the depsgraph; the redraw evaluates the
        # keys just written (frame_set would force a full update every tick).
        context.scene.frame_current = scene_frame


def finish_recording(context, settings) -> Tuple[bool, str]:
    """Stop the take and (optionally) bake/apply it. Returns (ok, message)."""
    from ..recording.session import get_active_session
    from .camera_ops import get_capture_armature

    session = get_active_session()
    was_recording = session.is_recording
    session.stop()
    settings.is_recording = False
    settings.is_paused = False
    settings.record_frame_count = session.frame_count()

    from ..overlay.viewport import update_overlay

    update_overlay(recording=False, paused=False, frame_count=session.frame_count())

    if not was_recording:
        return False, "Not recording"
    if session.frame_count() == 0:
        _reset_live_keyer()
        return False, "Recording stopped - no frames captured (was the body tracked and the rig mapped?)"

    messages = [f"{session.frame_count()} frames ({session.duration_seconds():.1f}s)"]
    if session.should_warn_tracking():
        messages.append(session.tracking_warning_message())

    arm = get_capture_armature(context, settings)
    if settings.auto_apply_on_stop and arm is not None:
        keyed_live = _LIVE_KEYER is not None and _LIVE_KEYER.frames_written > 0
        if not keyed_live:
            from ..bake.action import bake_session_to_action

            ok, msg, action = bake_session_to_action(
                session.frames,
                arm,
                action_name=settings.action_name,
                start_frame=settings.bake_start_frame,
                overwrite=settings.overwrite_action,
                rotation_mode=settings.rotation_mode,
            )
            if not ok:
                _reset_live_keyer()
                return False, msg
            settings.action_name = action.name
        action = bpy.data.actions.get(settings.action_name)
        if action is not None:
            from ..bake.apply import apply_action_to_armature

            apply_action_to_armature(arm, action.name, mode=settings.apply_mode, start_frame=settings.bake_start_frame)
            first = session.frames[0].frame_index
            last = session.frames[-1].frame_index
            scene = context.scene
            scene.frame_start = settings.bake_start_frame
            scene.frame_end = settings.bake_start_frame + (last - first)
            scene.frame_set(settings.bake_start_frame)
            messages.append(f"Action '{action.name}' on {arm.name}, frames {scene.frame_start}-{scene.frame_end}. Press Space to play")
    _reset_live_keyer()
    return True, " | ".join(messages)


class BODYMOCAP_OT_record_start(Operator):
    bl_idname = "bodymocap.record_start"
    bl_label = "Record"
    bl_description = (
        "Start recording after a short countdown. Starts the camera and auto-maps the rig if needed"
    )

    countdown: bpy.props.FloatProperty(name="Countdown", default=RECORD_COUNTDOWN_SECONDS, min=0.0, max=10.0) if bpy else None

    def execute(self, context):
        from ..recording.session import get_active_session
        from .camera_ops import get_capture_armature, get_live

        settings = context.scene.bodymocap
        if get_active_session().is_recording:
            self.report({"WARNING"}, "Already recording")
            return {"CANCELLED"}
        if get_capture_armature(context, settings) is None:
            self.report({"ERROR"}, "Select the armature you want to animate first")
            return {"CANCELLED"}

        if not settings.camera_active:
            result = bpy.ops.bodymocap.camera_start()
            if "RUNNING_MODAL" not in result and "FINISHED" not in result:
                return {"CANCELLED"}

        if self.countdown <= 0.0:
            ok, msg = begin_recording(context, settings)
            self.report({"INFO"} if ok else {"ERROR"}, msg)
            return {"FINISHED"} if ok else {"CANCELLED"}

        live = get_live()
        live.pending_record_at = time.time() + self.countdown
        live.loop_message = f"Get ready... recording in {int(self.countdown)}"
        settings.last_message = ""
        self.report({"INFO"}, f"Recording starts in {self.countdown:.0f}s - get into position")
        return {"FINISHED"}


class BODYMOCAP_OT_record_pause(Operator):
    bl_idname = "bodymocap.record_pause"
    bl_label = "Pause / Resume Recording"

    def execute(self, context):
        from ..overlay.viewport import update_overlay
        from ..recording.session import get_active_session

        settings = context.scene.bodymocap
        session = get_active_session()
        if not session.is_recording:
            self.report({"ERROR"}, "Not recording")
            return {"CANCELLED"}
        if session.is_paused:
            session.resume(time.time())
            settings.is_paused = False
            self.report({"INFO"}, "Recording resumed")
        else:
            session.pause(time.time())
            settings.is_paused = True
            self.report({"INFO"}, "Recording paused")
        update_overlay(paused=session.is_paused)
        return {"FINISHED"}


class BODYMOCAP_OT_record_stop(Operator):
    bl_idname = "bodymocap.record_stop"
    bl_label = "Stop Recording"
    bl_description = "Stop the take and apply it to the rig"

    def execute(self, context):
        from ..recording.session import get_active_session
        from .camera_ops import get_live

        settings = context.scene.bodymocap
        live = get_live()
        if live.pending_record_at is not None and not get_active_session().is_recording:
            live.pending_record_at = None
            settings.last_message = ""
            self.report({"INFO"}, "Countdown cancelled")
            return {"FINISHED"}
        live.pending_record_at = None
        ok, msg = finish_recording(context, settings)
        settings.last_message = msg if ok else ""
        if settings.stop_camera_on_stop and settings.camera_active:
            settings.camera_active = False
        self.report({"INFO"} if ok else {"WARNING"}, msg)
        return {"FINISHED"} if ok else {"CANCELLED"}


class BODYMOCAP_OT_record_discard(Operator):
    bl_idname = "bodymocap.record_discard"
    bl_label = "Discard Take"

    def execute(self, context):
        from ..overlay.viewport import update_overlay
        from ..recording.session import get_active_session
        from .camera_ops import get_live

        settings = context.scene.bodymocap
        get_live().pending_record_at = None
        session = get_active_session()
        session.discard()
        _reset_live_keyer()
        settings.is_recording = False
        settings.is_paused = False
        settings.record_frame_count = 0
        update_overlay(recording=False, paused=False, frame_count=0)
        self.report({"INFO"}, "Take discarded")
        return {"FINISHED"}


class BODYMOCAP_OT_quick_record(Operator):
    bl_idname = "bodymocap.quick_record"
    bl_label = "Record"
    bl_description = (
        "One click: start the camera, map the rig, count down and record; click again to stop "
        "and put the animation on the timeline"
    )

    def execute(self, context):
        from ..recording.session import get_active_session
        from .camera_ops import get_live

        settings = context.scene.bodymocap
        if get_active_session().is_recording or get_live().pending_record_at is not None:
            return bpy.ops.bodymocap.record_stop()
        return bpy.ops.bodymocap.record_start(countdown=RECORD_COUNTDOWN_SECONDS)


CLASSES = (
    BODYMOCAP_OT_record_start,
    BODYMOCAP_OT_record_pause,
    BODYMOCAP_OT_record_stop,
    BODYMOCAP_OT_record_discard,
    BODYMOCAP_OT_quick_record,
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

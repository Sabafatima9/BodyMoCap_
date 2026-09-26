"""Camera start/stop, calibration, and modal capture loop (FR-010–016)."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore

# Module state for modal operator
_BACKEND = None
_CALIBRATION_SAMPLES = []
_LAST_LANDMARKS = None
_LAST_POSE_FRAME = None
_POLICY = None
_CALIBRATION = None
_FRAME_COUNTER = 0
_LAST_TICK = 0.0


def get_runtime_calibration():
    return _CALIBRATION


def get_last_landmarks():
    return _LAST_LANDMARKS


def _make_backend(settings):
    from ..core.confidence import ConfidenceConfig
    from ..pose.mediapipe_backend import MediaPipeBackend, mediapipe_available
    from ..pose.mock_backend import MockBackend

    cfg = ConfidenceConfig(min_confidence=settings.min_confidence)
    if settings.pose_backend == "MEDIAPIPE":
        if not mediapipe_available():
            return None, (
                "MediaPipe not installed or has no usable pose API. "
                "Use Mock backend or install deps (INSTALL.md)."
            )
        be = MediaPipeBackend(cfg)
        # Model path resolves via add-on preference → bundled asset → download.
        if not be.initialize():
            return None, (
                getattr(be, "last_error", "") or "Failed to initialize MediaPipe Pose."
            )
        return be, ""
    be = MockBackend(
        fixture_path=settings.fixture_path or None,
        mode=settings.mock_mode,
        confidence_cfg=cfg,
    )
    be.initialize(fixture_path=settings.fixture_path or None, mode=settings.mock_mode)
    return be, ""


def _mapping_dict(settings) -> Dict[str, str]:
    return {e.role: e.bone_name for e in settings.mapping_entries if e.role and e.bone_name}


class BODYMOCAP_OT_camera_start(Operator):
    bl_idname = "bodymocap.camera_start"
    bl_label = "Start Camera"
    bl_description = "Start webcam (or mock) capture loop"

    _timer = None

    def execute(self, context):
        global _BACKEND, _POLICY, _FRAME_COUNTER, _LAST_TICK, _CALIBRATION_SAMPLES

        from ..camera.capture import get_capture
        from ..core.confidence import HoldInterpolatePolicy
        from ..utils.blender_compat import check_opencv, is_supported_blender, version_warning_message
        from ..utils.logging_util import log_info, reset_session_stats, update_session_stats

        if not is_supported_blender():
            self.report({"ERROR"}, version_warning_message())
            return {"CANCELLED"}

        settings = context.scene.bodymocap
        if settings.camera_active:
            self.report({"WARNING"}, "Camera already active")
            return {"CANCELLED"}

        backend, err = _make_backend(settings)
        if backend is None:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}

        use_real_camera = settings.pose_backend == "MEDIAPIPE"
        if use_real_camera:
            ok_cv, _ = check_opencv()
            if not ok_cv:
                self.report(
                    {"ERROR"},
                    "OpenCV required for camera. Install opencv-python-headless into Blender's Python. See INSTALL.md.",
                )
                backend.shutdown()
                return {"CANCELLED"}
            cap = get_capture()
            # A video file path takes precedence over the webcam device index —
            # lets users test with recorded footage or the scene's own assets.
            video_path = bpy.path.abspath(
                getattr(settings, "camera_video_path", "") or ""
            ).strip()
            source = video_path if video_path else settings.camera_device_index
            if not cap.open_source(source):
                self.report({"ERROR"}, cap.last_error or "Failed to open camera")
                backend.shutdown()
                return {"CANCELLED"}
        else:
            # Mock path — no camera device required
            log_info("Starting mock/offline pose loop (no camera)")

        _BACKEND = backend
        _POLICY = HoldInterpolatePolicy(mode=settings.lost_policy)
        _FRAME_COUNTER = 0
        _LAST_TICK = time.time()
        _CALIBRATION_SAMPLES = []
        reset_session_stats()
        update_session_stats(
            device_index=settings.camera_device_index if use_real_camera else -1,
            backend=backend.name,
        )

        settings.camera_active = True
        settings.tracking_status = "OK"
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.033, window=context.window)
        wm.modal_handler_add(self)
        self.report({"INFO"}, f"Capture started ({backend.name})")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        global _FRAME_COUNTER, _LAST_TICK, _LAST_LANDMARKS, _LAST_POSE_FRAME, _CALIBRATION

        settings = context.scene.bodymocap
        if not settings.camera_active:
            return self._finish(context, cancelled=False)

        if event.type == "ESC":
            return self._finish(context, cancelled=True)

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        from ..camera.capture import get_capture
        from ..camera.preview import ensure_preview_area, numpy_bgr_to_blender_image
        from ..core.types import TrackingState
        from ..mapping.apply_pose import apply_landmarks_to_rotations, apply_rotations_to_armature
        from ..overlay.draw import draw_skeleton_opencv
        from ..recording.session import get_active_session
        from ..utils.logging_util import record_frame, update_session_stats

        frame_bgr = None
        cap = get_capture()
        if settings.pose_backend == "MEDIAPIPE" and cap.is_open:
            ok, frame_bgr = cap.read()
            if not ok or frame_bgr is None:
                settings.tracking_status = "Lost"
                self.report({"WARNING"}, "Failed to read camera frame")
                return {"PASS_THROUGH"}
            if settings.mirror_preview:
                frame_bgr = cap.mirror_frame(frame_bgr)

        now = time.time()
        dt = max(now - _LAST_TICK, 1e-6)
        _LAST_TICK = now
        fps = 1.0 / dt
        update_session_stats(fps=fps)

        pose = _BACKEND.infer(frame_bgr, frame_index=_FRAME_COUNTER, timestamp=now)
        _FRAME_COUNTER += 1
        _LAST_POSE_FRAME = pose

        landmarks = pose.landmarks
        state = pose.tracking_state
        processed = _POLICY.process(landmarks, state) if _POLICY else landmarks
        if processed is not None:
            _LAST_LANDMARKS = processed
            landmarks = processed

        settings.tracking_status = state.name
        record_frame(low_confidence=(state != TrackingState.OK))

        # Overlay on preview
        if frame_bgr is not None:
            drawn = draw_skeleton_opencv(
                frame_bgr,
                landmarks,
                threshold=settings.min_confidence,
                enabled=settings.show_overlay,
            )
            numpy_bgr_to_blender_image(drawn)
            ensure_preview_area()

        # Live apply to armature
        role_map = _mapping_dict(settings)
        bone_rots = {}
        if settings.live_apply and role_map and landmarks:
            bone_rots = apply_landmarks_to_rotations(
                landmarks, role_map, get_runtime_calibration()
            )
            arm = context.active_object
            if arm and arm.type == "ARMATURE" and bone_rots:
                # Scale subject
                apply_rotations_to_armature(arm, bone_rots)

        # Recording
        session = get_active_session()
        if session.is_recording and not session.is_paused and bone_rots:
            session.append(
                frame_index=session.frame_count(),
                bone_rotations=bone_rots,
                tracking_state=state,
                timestamp=now,
            )
            settings.record_frame_count = session.frame_count()

        return {"PASS_THROUGH"}

    def _finish(self, context, cancelled=False):
        global _BACKEND
        settings = context.scene.bodymocap
        settings.camera_active = False
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        from ..camera.capture import get_capture

        get_capture().close()
        if _BACKEND:
            _BACKEND.shutdown()
            _BACKEND = None
        from ..utils.logging_util import log_info, session_summary

        log_info(session_summary())
        self.report({"INFO"}, "Camera stopped" if not cancelled else "Camera cancelled")
        return {"CANCELLED"} if cancelled else {"FINISHED"}


class BODYMOCAP_OT_camera_stop(Operator):
    bl_idname = "bodymocap.camera_stop"
    bl_label = "Stop Camera"

    def execute(self, context):
        settings = context.scene.bodymocap
        if not settings.camera_active:
            self.report({"WARNING"}, "Camera is not active")
            return {"CANCELLED"}
        settings.camera_active = False
        from ..camera.capture import get_capture

        get_capture().close()
        self.report({"INFO"}, "Camera stop requested")
        return {"FINISHED"}


class BODYMOCAP_OT_calibrate(Operator):
    bl_idname = "bodymocap.calibrate"
    bl_label = "Calibrate Rest Pose"
    bl_description = "Average landmarks over N seconds while holding T/A pose (FR-013–014)"

    _timer = None
    _start = 0.0
    _samples = None
    _backend = None
    _use_live = False

    def execute(self, context):
        global _CALIBRATION

        from ..utils.blender_compat import is_supported_blender, version_warning_message

        if not is_supported_blender():
            self.report({"ERROR"}, version_warning_message())
            return {"CANCELLED"}

        settings = context.scene.bodymocap
        self._samples = []
        self._start = time.time()
        self._use_live = bool(settings.camera_active and get_last_landmarks())

        if not self._use_live:
            backend, err = _make_backend(settings)
            if backend is None:
                self.report({"ERROR"}, err)
                return {"CANCELLED"}
            self._backend = backend
            # For MediaPipe without active camera, try open briefly
            if settings.pose_backend == "MEDIAPIPE":
                from ..camera.capture import get_capture
                from ..utils.blender_compat import check_opencv

                ok_cv, _ = check_opencv()
                if not ok_cv:
                    self.report({"ERROR"}, "OpenCV required for live calibration with MediaPipe.")
                    backend.shutdown()
                    return {"CANCELLED"}
                cap = get_capture()
                video_path = bpy.path.abspath(
                    getattr(settings, "camera_video_path", "") or ""
                ).strip()
                source = video_path if video_path else settings.camera_device_index
                if not cap.is_open and not cap.open_source(source):
                    self.report({"ERROR"}, cap.last_error or "Cannot open camera for calibration")
                    backend.shutdown()
                    return {"CANCELLED"}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self.report(
            {"INFO"},
            f"Calibrating {settings.rest_pose_style} for {settings.calibration_seconds:.1f}s — hold pose",
        )
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        global _CALIBRATION

        settings = context.scene.bodymocap
        if event.type == "ESC":
            return self._done(context, ok=False)

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        elapsed = time.time() - self._start
        landmarks = None
        if self._use_live:
            landmarks = get_last_landmarks()
        else:
            frame_bgr = None
            if settings.pose_backend == "MEDIAPIPE":
                from ..camera.capture import get_capture

                ok, frame_bgr = get_capture().read()
                if not ok:
                    self.report({"ERROR"}, "Lost camera during calibration")
                    return self._done(context, ok=False)
                if settings.mirror_preview:
                    frame_bgr = get_capture().mirror_frame(frame_bgr)
            pose = self._backend.infer(frame_bgr, frame_index=len(self._samples), timestamp=elapsed)
            landmarks = pose.landmarks

        if landmarks:
            self._samples.append(landmarks)

        if elapsed >= settings.calibration_seconds:
            from ..core.types import RestPoseStyle
            from ..mapping.apply_pose import average_calibrations

            if len(self._samples) < 3:
                self.report({"ERROR"}, "Not enough landmark samples for calibration")
                return self._done(context, ok=False)

            cal = average_calibrations(self._samples)
            cal.rest_style = RestPoseStyle[settings.rest_pose_style]
            # Apply subject scale prop
            cal.scale *= settings.subject_scale
            _CALIBRATION = cal
            settings.is_calibrated = cal.valid
            self.report(
                {"INFO"},
                f"Calibration complete ({len(self._samples)} samples, scale={cal.scale:.3f})",
            )
            return self._done(context, ok=True)

        return {"PASS_THROUGH"}

    def _done(self, context, ok=True):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        if self._backend and not context.scene.bodymocap.camera_active:
            self._backend.shutdown()
            # Don't close camera if user had it for other reasons; if we opened it alone:
            if not context.scene.bodymocap.camera_active:
                from ..camera.capture import get_capture

                # Only release if camera_active is false (we may have opened for calib)
                if context.scene.bodymocap.pose_backend == "MEDIAPIPE":
                    get_capture().close()
        return {"FINISHED"} if ok else {"CANCELLED"}


CLASSES = (
    BODYMOCAP_OT_camera_start,
    BODYMOCAP_OT_camera_stop,
    BODYMOCAP_OT_calibrate,
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

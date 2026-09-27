"""Camera start/stop, calibration, and modal capture loop (FR-010–016).

The capture loop runs as a modal operator on a ~30 Hz timer. Every tick:
read frame → pose inference → smoothing / hold policy → 3D solve → drive the rig →
(optionally) record + keyframe the timeline → refresh the viewport overlay.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:
    import bpy
    from bpy.types import Operator
except ImportError:
    bpy = None
    Operator = object  # type: ignore

from ..core.types import CalibrationData, PoseFrame, RootReference


class LiveCapture:
    """Mutable runtime state shared by the capture loop and the other operators."""

    def __init__(self):
        self.backend = None
        self.worker = None  # CaptureWorker for real cameras (background read + inference)
        self.last_sequence = -1
        self.policy = None
        self.smoother = None
        self.calibration: Optional[CalibrationData] = None
        self.root_reference: Optional[RootReference] = None
        self.last_landmarks = None  # smoothed, solve-space landmarks
        self.last_pose: Optional[PoseFrame] = None
        self.frame_counter = 0
        self.last_tick = 0.0
        self.fps = 0.0
        self.armature_name = ""
        self.pending_record_at: Optional[float] = None
        self.rig_scale: Optional[float] = None
        self.loop_message = ""  # transient hint from the capture loop (countdown, waiting for body...)
        self.calibration_message = ""  # set by the calibrate operator while it samples

    def reset_runtime(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.backend = None
        self.worker = None
        self.last_sequence = -1
        self.policy = None
        self.smoother = None
        self.last_landmarks = None
        self.last_pose = None
        self.frame_counter = 0
        self.fps = 0.0
        self.pending_record_at = None
        self.rig_scale = None
        self.loop_message = ""
        if self.calibration is None:
            self.root_reference = None


_LIVE = LiveCapture()


def get_live() -> LiveCapture:
    return _LIVE


def get_runtime_calibration():
    return _LIVE.calibration


def set_runtime_calibration(cal: Optional[CalibrationData]) -> None:
    _LIVE.calibration = cal
    _LIVE.root_reference = cal.root_reference if (cal and cal.root_reference.valid) else None
    _LIVE.rig_scale = None
    if _LIVE.smoother is not None:
        _LIVE.smoother.reset()


def get_last_landmarks():
    return _LIVE.last_landmarks


def get_last_pose_frame() -> Optional[PoseFrame]:
    return _LIVE.last_pose


def get_capture_armature(context, settings=None):
    """The rig being driven: explicit picker first, then the active armature."""
    settings = settings or context.scene.bodymocap
    arm = settings.capture_armature
    if arm is not None and arm.name in bpy.data.objects and arm.type == "ARMATURE":
        return arm
    obj = context.active_object if context else None
    if obj is not None and obj.type == "ARMATURE":
        return obj
    return None


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


def _camera_source(settings):
    video_path = bpy.path.abspath(getattr(settings, "camera_video_path", "") or "").strip()
    return video_path if video_path else settings.camera_device_index


def _ghost_points(arm, role_map, pose: PoseFrame, landmarks, live: LiveCapture, settings, root_offset):
    """World-space stick-figure points for the viewport ghost skeleton."""
    from mathutils import Vector

    from ..mapping.apply_pose import rotate_landmarks, to_blender_vec

    correction = live.calibration.world_correction if (live.calibration and live.calibration.valid) else None
    corrected = rotate_landmarks(landmarks, correction) if correction else landmarks
    scale = live.rig_scale or 1.0
    anchor = Vector((0.0, 0.0, 1.0))
    hips_bone = arm.data.bones.get(role_map.get("hips", "")) if arm else None
    if arm is not None and hips_bone is not None:
        anchor = arm.matrix_world @ hips_bone.head_local
    elif arm is not None:
        anchor = arm.matrix_world.translation.copy() + Vector((0.0, 0.0, 1.0))
    anchor = anchor + Vector((root_offset.x, root_offset.y, root_offset.z)) + Vector((settings.ghost_offset, 0.0, 0.0))
    points = []
    for name, lm in corrected.items():
        p = to_blender_vec(lm.position)
        world = anchor + Vector((p.x, p.y, p.z)) * scale
        points.append((name, (world.x, world.y, world.z), lm.confidence, lm.valid))
    return points


def _compute_rig_scale(arm, role_map, live: LiveCapture, landmarks) -> float:
    from ..mapping.apply_pose import resolve_landmark_position, rig_torso_length

    torso_m = live.calibration.torso_length if (live.calibration and live.calibration.valid) else 0.0
    if torso_m <= 1e-6:
        mid_h = resolve_landmark_position("hips_mid", landmarks)
        mid_s = resolve_landmark_position("shoulders_mid", landmarks)
        torso_m = (mid_s - mid_h).length() if (mid_h and mid_s) else 0.0
    rig_len = rig_torso_length(arm, role_map)
    if torso_m > 1e-6 and rig_len > 1e-6:
        return rig_len / torso_m
    return 1.0


class BODYMOCAP_OT_camera_start(Operator):
    bl_idname = "bodymocap.camera_start"
    bl_label = "Start Camera"
    bl_description = "Start webcam (or mock) capture: shows the camera in the viewport and drives the rig live"

    _timer = None

    def execute(self, context):
        from ..camera.capture import get_capture
        from ..core.confidence import HoldInterpolatePolicy
        from ..core.smoothing import LandmarkSmoother
        from ..overlay.viewport import register_viewport_overlay, update_overlay
        from ..utils.blender_compat import check_opencv, is_supported_blender, version_warning_message
        from ..utils.logging_util import log_info, reset_session_stats, update_session_stats

        if not is_supported_blender():
            self.report({"ERROR"}, version_warning_message())
            return {"CANCELLED"}

        settings = context.scene.bodymocap
        if settings.camera_active:
            self.report({"WARNING"}, "Camera already active")
            return {"CANCELLED"}

        arm = get_capture_armature(context, settings)
        if arm is not None:
            settings.capture_armature = arm
            if not _mapping_dict(settings):
                bpy.ops.bodymocap.auto_map()

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
            if not cap.open_source(_camera_source(settings)):
                self.report({"ERROR"}, cap.last_error or "Failed to open camera")
                backend.shutdown()
                return {"CANCELLED"}
        else:
            log_info("Starting mock/offline pose loop (no camera)")

        live = get_live()
        live.reset_runtime()
        live.backend = backend
        live.policy = HoldInterpolatePolicy(mode=settings.lost_policy)
        live.smoother = LandmarkSmoother(settings.smoothing)
        live.last_tick = time.time()
        live.armature_name = arm.name if arm else ""
        if use_real_camera:
            from ..camera.worker import CaptureWorker

            live.worker = CaptureWorker(get_capture(), backend, mirror=settings.mirror_preview)
            live.worker.start()
        reset_session_stats()
        update_session_stats(
            device_index=settings.camera_device_index if use_real_camera else -1,
            backend=backend.name,
        )

        settings.camera_active = True
        settings.tracking_status = "Starting"
        settings.last_message = ""
        register_viewport_overlay()
        update_overlay(status="Starting", fps=0.0, recording=False, has_image=False, threshold=settings.min_confidence)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.033, window=context.window)
        wm.modal_handler_add(self)
        if arm is None:
            self.report({"WARNING"}, f"Capture started ({backend.name}) - select an armature to drive it")
        else:
            self.report({"INFO"}, f"Capture started ({backend.name}) driving {arm.name}")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        settings = context.scene.bodymocap
        if not settings.camera_active:
            return self._finish(context, cancelled=False)

        # Only the timer drives us; every other event (incl. ESC) belongs to the user.
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        try:
            self._tick(context, settings)
        except Exception as exc:  # keep the loop alive; report once per error type
            from ..utils.logging_util import log_error

            log_error(f"capture tick failed: {exc!r}")
            settings.last_message = f"Error: {exc}"
        return {"PASS_THROUGH"}

    def _tick(self, context, settings):
        from ..camera.preview import ensure_preview_area, rgba_pixels_to_blender_image
        from ..core.types import TrackingState, Vec3
        from ..mapping.apply_pose import (
            apply_solution_to_armature,
            build_root_reference,
            solve_pose,
        )
        from ..overlay.viewport import tag_redraw_view3d, update_overlay
        from ..recording.session import get_active_session
        from ..utils.logging_util import record_frame, update_session_stats

        live = get_live()
        preview = None
        now = time.time()
        if live.worker is not None:
            # Real camera: frames, inference and the preview pixels come from the worker.
            worker = live.worker
            worker.mirror = settings.mirror_preview
            worker.make_preview = settings.show_camera_in_viewport or settings.show_overlay
            worker.draw_overlay = settings.show_overlay
            worker.overlay_threshold = settings.min_confidence
            result = worker.latest(live.last_sequence)
            if result is None:
                if worker.last_error and worker.read_failures > 30:
                    settings.tracking_status = "Lost"
                    settings.last_message = worker.last_error
                    update_overlay(status="Lost", message=worker.last_error)
                    tag_redraw_view3d()
                return
            live.last_sequence = result.sequence
            preview = result.preview
            pose = result.pose
            now = result.timestamp
            live.fps = worker.inference_fps
        else:
            pose = live.backend.infer(None, frame_index=live.frame_counter, timestamp=now)
            dt = max(now - live.last_tick, 1e-6)
            live.fps = live.fps * 0.8 + (1.0 / dt) * 0.2 if live.fps else 1.0 / dt
        live.last_tick = now
        settings.capture_fps = live.fps
        update_session_stats(fps=live.fps)
        live.frame_counter += 1
        live.last_pose = pose

        state = pose.tracking_state
        image_landmarks = pose.landmarks
        solve_landmarks = pose.solve_landmarks()
        processed = live.policy.process(solve_landmarks, state) if live.policy else solve_landmarks
        if processed is not None:
            if live.smoother is not None:
                live.smoother.strength = settings.smoothing
                processed = live.smoother.process(processed)
            live.last_landmarks = processed
        landmarks = processed if processed is not None else {}

        settings.tracking_status = state.name
        record_frame(low_confidence=(state != TrackingState.OK))

        # Camera preview image (Image Editor + viewport picture-in-picture)
        has_image = False
        if preview is not None:
            flat, w, h = preview
            has_image = rgba_pixels_to_blender_image(flat, w, h) is not None
            ensure_preview_area()

        # Root reference: calibration first, else the first well-tracked frame
        if (
            live.root_reference is None
            and state == TrackingState.OK
            and landmarks
            and image_landmarks
            and pose.world_landmarks
        ):
            ref = build_root_reference(image_landmarks, landmarks, pose.aspect, settings.subject_distance)
            if ref.valid:
                live.root_reference = ref

        # Drive the rig
        role_map = _mapping_dict(settings)
        arm = get_capture_armature(context, settings)
        solution = None
        root_offset = Vec3()
        if settings.live_apply and role_map and landmarks and arm is not None:
            if live.rig_scale is None:
                live.rig_scale = _compute_rig_scale(arm, role_map, live, landmarks)
            solution = solve_pose(
                landmarks,
                role_map,
                live.calibration,
                arm,
                image_landmarks=image_landmarks,
                aspect=pose.aspect,
                root_reference=live.root_reference,
                root_motion=settings.root_motion,
                root_scale=settings.root_motion_scale * settings.subject_scale,
                rig_scale=live.rig_scale,
            )
            if solution:
                apply_solution_to_armature(arm, solution)
                root_offset = solution.root_offset
            if not settings.root_motion:
                hips = arm.pose.bones.get(role_map.get("hips", ""))
                if hips is not None and hips.location.length > 0.0:
                    hips.location = (0.0, 0.0, 0.0)

        # Countdown → recording
        message = ""
        if live.pending_record_at is not None:
            remaining = live.pending_record_at - now
            if remaining <= 0.0:
                live.pending_record_at = None
                from .record_ops import begin_recording

                ok, msg = begin_recording(context, settings)
                message = msg if not ok else ""
            else:
                message = f"Get ready... recording in {int(remaining) + 1}"

        # Recording (+ live keyframes)
        session = get_active_session()
        if session.is_recording and not session.is_paused and solution:
            frame = session.append(
                bone_rotations=solution.rotations,
                tracking_state=state,
                timestamp=now,
                bone_locations=solution.locations,
            )
            settings.record_frame_count = session.frame_count()
            if frame is not None:
                from .record_ops import key_live_frame

                key_live_frame(context, settings, arm, frame)
        elif session.is_recording and not solution and not message:
            message = "Recording: waiting for the body to be tracked"

        if arm is None and not message:
            message = "Select an armature to drive"
        elif not role_map and arm is not None and not message:
            message = "No bone mapping - click Auto-Map"
        if live.calibration_message:
            message = live.calibration_message

        # Viewport overlay data
        landmarks_2d = {
            name: (lm.position.x, lm.position.y, lm.confidence, lm.valid)
            for name, lm in image_landmarks.items()
        }
        ghost = []
        if settings.show_ghost_skeleton and landmarks and arm is not None:
            ghost = _ghost_points(arm, role_map, pose, landmarks, live, settings, root_offset)
        update_overlay(
            landmarks_2d=landmarks_2d,
            ghost=ghost,
            status=state.name,
            fps=live.fps,
            recording=session.is_recording,
            paused=session.is_paused,
            frame_count=session.frame_count(),
            has_image=has_image,
            threshold=settings.min_confidence,
            message=message,
        )
        live.loop_message = message
        tag_redraw_view3d()

    def _finish(self, context, cancelled=False):
        from ..camera.capture import get_capture
        from ..overlay.viewport import unregister_viewport_overlay
        from ..recording.session import get_active_session
        from ..utils.logging_util import log_info, session_summary

        settings = context.scene.bodymocap
        if get_active_session().is_recording:
            try:
                bpy.ops.bodymocap.record_stop()
            except Exception:
                pass
        settings.camera_active = False
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        live = get_live()
        if live.worker is not None:
            live.worker.stop()  # join the reader thread before releasing the device
            live.worker = None
        get_capture().close()
        if live.backend:
            live.backend.shutdown()
        live.reset_runtime()
        unregister_viewport_overlay()

        log_info(session_summary())
        settings.tracking_status = "Stopped"
        self.report({"INFO"}, "Camera stopped" if not cancelled else "Camera cancelled")
        return {"CANCELLED"} if cancelled else {"FINISHED"}


class BODYMOCAP_OT_camera_stop(Operator):
    bl_idname = "bodymocap.camera_stop"
    bl_label = "Stop Camera"
    bl_description = "Stop the capture loop and release the camera"

    def execute(self, context):
        settings = context.scene.bodymocap
        if not settings.camera_active:
            self.report({"WARNING"}, "Camera is not active")
            return {"CANCELLED"}
        # The modal loop notices the flag on its next tick and releases everything.
        settings.camera_active = False
        self.report({"INFO"}, "Camera stop requested")
        return {"FINISHED"}


class BODYMOCAP_OT_calibrate(Operator):
    bl_idname = "bodymocap.calibrate"
    bl_label = "Calibrate Rest Pose"
    bl_description = (
        "Hold a T/A pose facing the camera for a few seconds: fixes camera tilt, your facing "
        "direction and body scale so the rig follows you in 3D (FR-013–014)"
    )

    _timer = None
    _start = 0.0
    _samples = None
    _image_samples = None
    _aspect = 1.0
    _backend = None
    _use_live = False

    def execute(self, context):
        from ..utils.blender_compat import is_supported_blender, version_warning_message

        if not is_supported_blender():
            self.report({"ERROR"}, version_warning_message())
            return {"CANCELLED"}

        settings = context.scene.bodymocap
        self._samples = []
        self._image_samples = []
        self._start = time.time()
        self._use_live = bool(settings.camera_active)

        if not self._use_live:
            backend, err = _make_backend(settings)
            if backend is None:
                self.report({"ERROR"}, err)
                return {"CANCELLED"}
            self._backend = backend
            if settings.pose_backend == "MEDIAPIPE":
                from ..camera.capture import get_capture
                from ..utils.blender_compat import check_opencv

                ok_cv, _ = check_opencv()
                if not ok_cv:
                    self.report({"ERROR"}, "OpenCV required for live calibration with MediaPipe.")
                    backend.shutdown()
                    return {"CANCELLED"}
                cap = get_capture()
                if not cap.is_open and not cap.open_source(_camera_source(settings)):
                    self.report({"ERROR"}, cap.last_error or "Cannot open camera for calibration")
                    backend.shutdown()
                    return {"CANCELLED"}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self.report(
            {"INFO"},
            f"Calibrating {settings.rest_pose_style} for {settings.calibration_seconds:.1f}s - hold the pose",
        )
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        settings = context.scene.bodymocap
        if event.type == "ESC":
            return self._done(context, ok=False)

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        elapsed = time.time() - self._start
        pose = None
        if self._use_live:
            pose = get_last_pose_frame()
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

        if pose is not None and pose.landmarks:
            solve = pose.solve_landmarks()
            if any(lm.valid for lm in solve.values()):
                self._samples.append(solve)
                self._image_samples.append(pose.landmarks)
                self._aspect = pose.aspect
        remaining = settings.calibration_seconds - elapsed
        live = get_live()
        live.calibration_message = f"Calibrating... hold still ({max(0.0, remaining):.1f}s)"
        settings.last_message = live.calibration_message
        from ..overlay.viewport import tag_redraw_view3d, update_overlay

        update_overlay(message=live.calibration_message)
        tag_redraw_view3d()

        if elapsed >= settings.calibration_seconds:
            from ..core.types import RestPoseStyle
            from ..mapping.apply_pose import average_calibrations

            if len(self._samples) < 3:
                settings.last_message = "Calibration failed: body not tracked"
                self.report({"ERROR"}, "Not enough landmark samples for calibration - stand fully in view")
                return self._done(context, ok=False)

            cal = average_calibrations(
                self._samples,
                self._image_samples,
                aspect=self._aspect,
                distance=settings.subject_distance,
            )
            cal.rest_style = RestPoseStyle[settings.rest_pose_style]
            cal.scale *= settings.subject_scale
            set_runtime_calibration(cal)
            settings.is_calibrated = cal.valid
            settings.last_message = f"Calibrated (torso {cal.torso_length:.2f} m)"
            self.report(
                {"INFO"},
                f"Calibration complete ({len(self._samples)} samples, torso {cal.torso_length:.2f} m)",
            )
            return self._done(context, ok=True)

        return {"PASS_THROUGH"}

    def _done(self, context, ok=True):
        from ..overlay.viewport import update_overlay

        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        get_live().calibration_message = ""
        update_overlay(message="")
        settings = context.scene.bodymocap
        if self._backend is not None and not settings.camera_active:
            self._backend.shutdown()
            if settings.pose_backend == "MEDIAPIPE":
                from ..camera.capture import get_capture

                get_capture().close()
        self._backend = None
        return {"FINISHED"} if ok else {"CANCELLED"}


class BODYMOCAP_OT_reset_calibration(Operator):
    bl_idname = "bodymocap.reset_calibration"
    bl_label = "Reset Calibration"
    bl_description = "Forget the calibration and root reference"

    def execute(self, context):
        set_runtime_calibration(None)
        get_live().root_reference = None
        context.scene.bodymocap.is_calibrated = False
        self.report({"INFO"}, "Calibration reset")
        return {"FINISHED"}


CLASSES = (
    BODYMOCAP_OT_camera_start,
    BODYMOCAP_OT_camera_stop,
    BODYMOCAP_OT_calibrate,
    BODYMOCAP_OT_reset_calibration,
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

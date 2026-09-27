"""Background capture + inference worker (FR-016: never block Blender's UI thread).

``cv2.VideoCapture.read`` blocks until the webcam delivers its next frame (~33 ms
at 30 fps) and pose inference costs another ~30 ms. Doing both inside the modal
timer halves the effective frame rate and makes the viewport stutter. The worker
runs them on a daemon thread and keeps only the newest result; the capture loop
polls :meth:`CaptureWorker.latest` and stays cheap.

Only pure-Python / OpenCV / MediaPipe objects are touched here — never ``bpy``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from ..core.types import PoseFrame


@dataclass
class WorkerResult:
    frame_bgr: Any
    pose: PoseFrame
    timestamp: float
    sequence: int
    preview: Optional[Tuple[Any, int, int]] = None  # (flat RGBA float32, w, h) ready for Image.pixels


class CaptureWorker:
    """Reads frames from ``capture`` and runs ``backend.infer`` on a background thread."""

    def __init__(self, capture, backend, mirror: bool = False):
        self._capture = capture
        self._backend = backend
        self.mirror = mirror
        # Preview settings, updated by the capture loop each tick
        self.make_preview = True
        self.draw_overlay = True
        self.overlay_threshold = 0.5
        self._lock = threading.Lock()
        self._latest: Optional[WorkerResult] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sequence = 0
        self.last_error = ""
        self.read_failures = 0
        self.inference_fps = 0.0

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="BodyMocapCapture", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- data ----------------------------------------------------------------
    def latest(self, after_sequence: int = -1) -> Optional[WorkerResult]:
        """Newest result, or None if nothing newer than ``after_sequence`` exists."""
        with self._lock:
            result = self._latest
        if result is None or result.sequence <= after_sequence:
            return None
        return result

    # -- thread body ---------------------------------------------------------
    def _run(self) -> None:
        last = time.time()
        while not self._stop.is_set():
            try:
                ok, frame = self._capture.read()
            except Exception as exc:
                self.last_error = f"camera read error: {exc}"
                ok, frame = False, None
            if not ok or frame is None:
                self.read_failures += 1
                if self.read_failures > 30:
                    self.last_error = self.last_error or "camera stopped delivering frames"
                time.sleep(0.02)
                continue
            self.read_failures = 0
            if self.mirror:
                frame = self._capture.mirror_frame(frame)
            now = time.time()
            try:
                pose = self._backend.infer(frame, frame_index=self._sequence, timestamp=now)
            except Exception as exc:
                self.last_error = f"inference error: {exc}"
                pose = PoseFrame(frame_index=self._sequence, timestamp=now)
            dt = max(now - last, 1e-6)
            last = now
            self.inference_fps = self.inference_fps * 0.8 + (1.0 / dt) * 0.2 if self.inference_fps else 1.0 / dt
            preview = None
            if self.make_preview:
                try:
                    from .preview import bgr_to_rgba_pixels
                    from ..overlay.draw import draw_skeleton_opencv

                    drawn = draw_skeleton_opencv(
                        frame, pose.landmarks, threshold=self.overlay_threshold, enabled=self.draw_overlay
                    )
                    preview = bgr_to_rgba_pixels(drawn)
                except Exception as exc:
                    self.last_error = f"preview error: {exc}"
            self._sequence += 1
            with self._lock:
                self._latest = WorkerResult(frame, pose, now, self._sequence, preview)

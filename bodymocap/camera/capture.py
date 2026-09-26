"""OpenCV camera/video capture helpers (FR-010–016). bpy-guarded where needed.

Sources:
- integer device index (webcam) — tries Windows-friendly backends first
- file path / URL string — opens a video file (useful for offline testing)
"""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple, Union

from ..utils.logging_util import log_error, log_info


def _candidate_backends() -> list:
    """Capture backend preference order for device indices."""
    try:
        import cv2
    except ImportError:
        return []
    if os.name == "nt":
        # DirectShow is most reliable on Windows; Media Foundation next.
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    return [cv2.CAP_ANY]


class CameraCapture:
    """Wraps cv2.VideoCapture by device index or video file path."""

    def __init__(self):
        self._cap = None
        self.device_index: int = 0
        self.is_open: bool = False
        self.last_error: str = ""
        self.source_desc: str = ""
        self.backend_name: str = ""

    def open(self, device_index: int = 0, width: int = 640, height: int = 480) -> bool:
        return self.open_source(int(device_index), width=width, height=height)

    def open_source(
        self,
        source: Union[int, str],
        width: int = 640,
        height: int = 480,
    ) -> bool:
        """Open a camera index (int) or a video file path / URL (str)."""
        try:
            import cv2
        except ImportError:
            self.last_error = (
                "OpenCV not installed. Install opencv-python-headless into Blender's Python. "
                "See INSTALL.md."
            )
            log_error(self.last_error)
            return False

        self.close()

        is_file = isinstance(source, str) and source.strip() != ""
        backends = _candidate_backends()
        if not backends:
            self.last_error = "OpenCV has no usable capture backends."
            return False

        if is_file:
            self.source_desc = f"file '{source}'"
            attempts = [(source.strip(), b) for b in backends]
        else:
            idx = int(source)
            self.device_index = idx
            self.source_desc = f"camera {idx}"
            attempts = [(idx, b) for b in backends]

        last_err = ""
        for src, backend in attempts:
            try:
                cap = cv2.VideoCapture(src, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                ok, _ = cap.read()
                if not ok:
                    last_err = (
                        f"{self.source_desc} opened but failed to read a frame."
                    )
                    cap.release()
                    continue
                self._cap = cap
                self.is_open = True
                self.last_error = ""
                self.backend_name = self._backend_name(cv2, backend)
                log_info(f"Opened {self.source_desc} via {self.backend_name}")
                return True
            except Exception as exc:
                last_err = f"Capture open error on {self.source_desc}: {exc}"

        if is_file:
            self.last_error = (
                last_err
                or f"Failed to open video source '{source}'. Check the path is readable."
            )
        else:
            self.last_error = (
                last_err
                or f"Failed to open camera device index {source}. "
                "Check that a webcam is connected and not in use by another app."
            )
        log_error(self.last_error)
        return False

    @staticmethod
    def _backend_name(cv2: Any, backend: int) -> str:
        for name in ("CAP_DSHOW", "CAP_MSMF", "CAP_V4L2", "CAP_ANY"):
            if getattr(cv2, name, None) == backend:
                return name
        return str(backend)

    def read(self) -> Tuple[bool, Any]:
        if not self.is_open or self._cap is None:
            return False, None
        try:
            ok, frame = self._cap.read()
            # Video files loop back to the start when exhausted
            if not ok and self.source_desc.startswith("file"):
                try:
                    import cv2

                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = self._cap.read()
                except Exception:
                    pass
            return ok, frame
        except Exception as exc:
            self.last_error = str(exc)
            return False, None

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self.is_open = False
        self.backend_name = ""
        log_info("Camera released")

    def mirror_frame(self, frame_bgr: Any) -> Any:
        try:
            import cv2

            return cv2.flip(frame_bgr, 1)
        except Exception:
            return frame_bgr


# Process-wide capture used by modal operator
_CAPTURE: Optional[CameraCapture] = None


def get_capture() -> CameraCapture:
    global _CAPTURE
    if _CAPTURE is None:
        _CAPTURE = CameraCapture()
    return _CAPTURE

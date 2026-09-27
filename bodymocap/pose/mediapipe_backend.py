"""MediaPipe Pose backend — optional dependency (FR-020–024, FR-082).

Supports both MediaPipe APIs:

- ``mediapipe.solutions.pose`` — legacy API (mediapipe 0.10.x)
- ``mediapipe.tasks.python.vision.PoseLandmarker`` — Tasks API (mediapipe 1.x,
  required on Python 3.13 / Blender 5.x builds)

The Tasks API needs a ``pose_landmarker*.task`` model file. Resolution order:

1. ``model_path`` kwarg to ``initialize()``
2. ``BODYMOCAP_POSE_MODEL`` environment variable
3. Add-on preference ``pose_model_path``
4. ``bodymocap/assets/pose_landmarker_full.task`` (bundled)
5. ``~/.bodymocap/models/pose_landmarker_full.task`` (auto-downloaded cache)
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..core.confidence import ConfidenceConfig, TrackingHysteresis
from ..core.landmarks import MEDIAPIPE_POSE_NAMES
from ..core.types import Landmark, PoseFrame, Vec3
from .backend import PoseBackend

_MODEL_FILENAMES = (
    "pose_landmarker_full.task",
    "pose_landmarker_heavy.task",
    "pose_landmarker_lite.task",
    "pose_landmarker.task",
)


def _import_mediapipe():
    try:
        import mediapipe as mp

        return mp
    except ImportError:
        return None
    except Exception:
        # mediapipe can raise non-ImportError errors on ABI mismatch
        return None


def mediapipe_available() -> bool:
    mp = _import_mediapipe()
    if mp is None:
        return False
    try:
        if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
            return True
    except Exception:
        pass
    try:
        from mediapipe.tasks.python import vision

        return hasattr(vision, "PoseLandmarker")
    except Exception:
        return False


def _addon_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _candidate_model_dirs() -> list:
    dirs = [_addon_dir() / "assets"]
    try:
        import bpy  # noqa: F401

        # Blender user data dir — survives add-on reinstalls
        try:
            user_data = Path(bpy.utils.user_resource("DATAFILES")) / "bodymocap" / "models"
            dirs.append(user_data)
        except Exception:
            pass
    except ImportError:
        pass
    dirs.append(Path.home() / ".bodymocap" / "models")
    return dirs


def _addon_pref_model_path() -> str:
    try:
        import bpy

        prefs = bpy.context.preferences
        pkg = __package__.split(".")[0] if __package__ else "bodymocap"
        addon = prefs.addons.get(pkg)
        if addon and addon.preferences:
            return getattr(addon.preferences, "pose_model_path", "") or ""
    except Exception:
        pass
    return ""


def resolve_pose_model_path(
    explicit: Optional[str] = None,
    download: bool = True,
) -> Optional[str]:
    """Locate (or fetch) a pose_landmarker .task file. Returns path or None."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("BODYMOCAP_POSE_MODEL", "")
    if env:
        candidates.append(env)
    pref = _addon_pref_model_path()
    if pref:
        candidates.append(pref)

    for c in candidates:
        try:
            p = Path(os.path.expanduser(os.path.expandvars(c)))
            if p.is_file() and p.stat().st_size > 100_000:
                return str(p)
        except Exception:
            continue

    # Search bundled + user model dirs
    for d in _candidate_model_dirs():
        for name in _MODEL_FILENAMES:
            p = d / name
            if p.is_file() and p.stat().st_size > 100_000:
                return str(p)

    if not download:
        return None
    return download_pose_model()


def download_pose_model(dest_dir: Optional[Path] = None) -> Optional[str]:
    """Download the official pose_landmarker_full.task once. Returns path."""
    from ..utils.blender_compat import POSE_MODEL_NAME, POSE_MODEL_URL
    from ..utils.logging_util import log_info, log_warning

    if dest_dir is None:
        dirs = _candidate_model_dirs()
        # Prefer user-writable cache (add-on dir may be read-only)
        dest_dir = dirs[-1] if dirs else Path.home() / ".bodymocap" / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / POSE_MODEL_NAME
    if dest.is_file() and dest.stat().st_size > 100_000:
        return str(dest)
    try:
        log_info(f"Downloading pose model from {POSE_MODEL_URL} ...")
        urllib.request.urlretrieve(POSE_MODEL_URL, str(dest))
        if dest.is_file() and dest.stat().st_size > 100_000:
            log_info(f"Pose model saved to {dest}")
            return str(dest)
    except Exception as exc:
        log_warning(f"Pose model download failed: {exc}")
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
    return None


class MediaPipeBackend(PoseBackend):
    name = "mediapipe"

    def __init__(self, confidence_cfg: Optional[ConfidenceConfig] = None):
        self._pose = None  # legacy Pose or PoseLandmarker
        self._mp = None
        self._api = ""  # "legacy" | "tasks"
        self._last_ts_ms = -1
        self._hyst = TrackingHysteresis(confidence_cfg or ConfidenceConfig())
        self._ready = False
        self.last_error = ""

    def is_available(self) -> bool:
        return mediapipe_available()

    def initialize(self, **kwargs: Any) -> bool:
        mp = _import_mediapipe()
        if mp is None:
            self.last_error = (
                "MediaPipe not installed. Install mediapipe into Blender's "
                "Python (see INSTALL.md)."
            )
            return False
        self._mp = mp

        # Legacy solutions API (mediapipe 0.x)
        try:
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
                self._pose = mp.solutions.pose.Pose(
                    static_image_mode=False,
                    model_complexity=int(kwargs.get("model_complexity", 1)),
                    enable_segmentation=False,
                    min_detection_confidence=float(
                        kwargs.get("min_detection_confidence", 0.5)
                    ),
                    min_tracking_confidence=float(
                        kwargs.get("min_tracking_confidence", 0.5)
                    ),
                )
                self._api = "legacy"
                self._ready = True
                self.last_error = ""
                return True
        except Exception as exc:
            self.last_error = f"MediaPipe solutions init failed: {exc}"
            self._pose = None

        # Tasks API (mediapipe 1.x)
        try:
            from mediapipe.tasks.python import vision
        except Exception as exc:
            self.last_error = (
                f"MediaPipe {getattr(mp, '__version__', '?')} has no usable pose "
                f"API (tried solutions and tasks): {exc}"
            )
            return False

        model_path = resolve_pose_model_path(kwargs.get("model_path"))
        if not model_path:
            self.last_error = (
                "MediaPipe Tasks API requires a pose_landmarker .task model "
                "file. Bundle bodymocap/assets/pose_landmarker_full.task, set "
                "the add-on preference 'Pose Model Path', or set env var "
                "BODYMOCAP_POSE_MODEL."
            )
            return False

        try:
            base = mp.tasks.BaseOptions(model_asset_path=model_path)
            opts = vision.PoseLandmarkerOptions(
                base_options=base,
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=float(
                    kwargs.get("min_detection_confidence", 0.5)
                ),
                min_pose_presence_confidence=float(
                    kwargs.get("min_pose_presence_confidence", 0.5)
                ),
                min_tracking_confidence=float(
                    kwargs.get("min_tracking_confidence", 0.5)
                ),
                output_segmentation_masks=False,
            )
            self._pose = vision.PoseLandmarker.create_from_options(opts)
            self._api = "tasks"
            self._ready = True
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = f"PoseLandmarker init failed: {exc}"
            self._pose = None
            self._ready = False
            return False

    def infer(self, frame_bgr: Any, frame_index: int = 0, timestamp: float = 0.0) -> PoseFrame:
        if not self._ready or self._pose is None:
            return PoseFrame(frame_index=frame_index, timestamp=timestamp)

        try:
            import cv2

            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            if self._api == "tasks":
                landmarks, world = self._infer_tasks(rgb)
            else:
                landmarks, world = self._infer_legacy(rgb)
        except Exception as exc:
            self.last_error = f"Inference error: {exc}"
            return PoseFrame(frame_index=frame_index, timestamp=timestamp)

        filtered = self._hyst.filter_landmarks(landmarks)
        state = self._hyst.update(landmarks)
        # World landmarks share validity with their image-space twins.
        world_filtered = {
            name: Landmark(name, lm.position, lm.confidence, filtered[name].valid if name in filtered else lm.valid)
            for name, lm in world.items()
        }
        return PoseFrame(
            landmarks=filtered,
            tracking_state=state,
            timestamp=timestamp,
            frame_index=frame_index,
            world_landmarks=world_filtered,
            aspect=(w / h) if h else 1.0,
        )

    @staticmethod
    def _confidence(lm: Any) -> float:
        vis = getattr(lm, "visibility", None)
        if vis is None:
            vis = getattr(lm, "presence", None)
        return float(vis) if vis is not None else 1.0

    @classmethod
    def _convert(cls, points: Any) -> Tuple[Dict[str, Landmark], Dict[str, Landmark]]:
        """Image-normalized landmarks → (image-space dict, empty world dict)."""
        landmarks: Dict[str, Landmark] = {}
        for idx, lm in enumerate(points):
            name = MEDIAPIPE_POSE_NAMES.get(idx, f"lm_{idx}")
            # MediaPipe: x,y normalized image (y down); z depth-ish (negative = closer).
            # Convert to x right, y up, z toward camera.
            landmarks[name] = Landmark(
                name=name,
                position=Vec3(float(lm.x - 0.5), float(1.0 - lm.y), float(-lm.z)),
                confidence=cls._confidence(lm),
                valid=True,
            )
        return landmarks, {}

    @classmethod
    def _convert_world(cls, points: Any) -> Dict[str, Landmark]:
        """Metric world landmarks (metres, hip-centred): x right, y down, z away → y up, z toward camera."""
        world: Dict[str, Landmark] = {}
        for idx, lm in enumerate(points):
            name = MEDIAPIPE_POSE_NAMES.get(idx, f"lm_{idx}")
            world[name] = Landmark(
                name=name,
                position=Vec3(float(lm.x), float(-lm.y), float(-lm.z)),
                confidence=cls._confidence(lm),
                valid=True,
            )
        return world

    def _infer_legacy(self, rgb: Any) -> Tuple[Dict[str, Landmark], Dict[str, Landmark]]:
        rgb.flags.writeable = False
        results = self._pose.process(rgb)
        if not results.pose_landmarks:
            return {}, {}
        landmarks, _ = self._convert(results.pose_landmarks.landmark)
        world_lms = getattr(results, "pose_world_landmarks", None)
        world = self._convert_world(world_lms.landmark) if world_lms else {}
        return landmarks, world

    def _infer_tasks(self, rgb: Any) -> Tuple[Dict[str, Landmark], Dict[str, Landmark]]:
        mp = self._mp
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        # detect_for_video requires strictly increasing timestamps (ms)
        import time

        ts_ms = int(time.monotonic() * 1000)
        if ts_ms <= self._last_ts_ms:
            ts_ms = self._last_ts_ms + 1
        self._last_ts_ms = ts_ms

        result = self._pose.detect_for_video(mp_image, ts_ms)
        poses = getattr(result, "pose_landmarks", None) or []
        if not poses:
            return {}, {}
        landmarks, _ = self._convert(poses[0])
        world_poses = getattr(result, "pose_world_landmarks", None) or []
        world = self._convert_world(world_poses[0]) if world_poses else {}
        return landmarks, world

    def shutdown(self) -> None:
        if self._pose is not None:
            try:
                self._pose.close()
            except Exception:
                pass
        self._pose = None
        self._ready = False

    def info(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "local": "true",
            "available": str(self.is_available()),
            "api": self._api or "none",
        }

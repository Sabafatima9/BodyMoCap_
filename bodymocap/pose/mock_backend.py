"""Deterministic mock / fixture pose backend for offline tests (FR-020–024)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.confidence import ConfidenceConfig, TrackingHysteresis
from ..core.landmarks import MEDIAPIPE_POSE_NAMES
from ..core.types import Landmark, PoseFrame, TrackingState, Vec3
from .backend import PoseBackend


def _idle_skeleton(t: float = 0.0) -> Dict[str, Landmark]:
    """Synthesize a standing idle humanoid in normalized coords."""
    sway = 0.02 * math.sin(t * 1.5)
    landmarks: Dict[str, Landmark] = {}

    def add(name: str, x: float, y: float, z: float, c: float = 0.95) -> None:
        landmarks[name] = Landmark(name, Vec3(x + sway, y, z), c, True)

    # MediaPipe-like: y down in image space; we use y-up world-ish for mocap
    add("nose", 0.0, 1.6, 0.0)
    add("left_eye", 0.03, 1.62, 0.02)
    add("right_eye", -0.03, 1.62, 0.02)
    add("left_ear", 0.08, 1.6, 0.0)
    add("right_ear", -0.08, 1.6, 0.0)
    add("left_shoulder", 0.2, 1.4, 0.0)
    add("right_shoulder", -0.2, 1.4, 0.0)
    add("left_elbow", 0.35, 1.15, 0.05)
    add("right_elbow", -0.35, 1.15, 0.05)
    add("left_wrist", 0.4, 0.9, 0.08)
    add("right_wrist", -0.4, 0.9, 0.08)
    add("left_index", 0.42, 0.85, 0.1)
    add("right_index", -0.42, 0.85, 0.1)
    add("left_hip", 0.1, 0.95, 0.0)
    add("right_hip", -0.1, 0.95, 0.0)
    add("left_knee", 0.12, 0.5, 0.02)
    add("right_knee", -0.12, 0.5, 0.02)
    add("left_ankle", 0.12, 0.05, 0.0)
    add("right_ankle", -0.12, 0.05, 0.0)
    add("left_foot_index", 0.14, 0.02, 0.08)
    add("right_foot_index", -0.14, 0.02, 0.08)
    add("left_heel", 0.11, 0.03, -0.04)
    add("right_heel", -0.11, 0.03, -0.04)
    return landmarks


def _walking_skeleton(t: float) -> Dict[str, Landmark]:
    """Simple walk cycle synthetic pose."""
    base = _idle_skeleton(t)
    phase = t * 2.5
    leg = 0.12 * math.sin(phase)
    arm = 0.1 * math.sin(phase + math.pi)

    def bump(name: str, dx: float = 0, dy: float = 0, dz: float = 0) -> None:
        if name in base:
            p = base[name].position
            base[name] = Landmark(
                name, Vec3(p.x + dx, p.y + dy, p.z + dz), base[name].confidence, True
            )

    bump("left_knee", 0, 0, leg)
    bump("left_ankle", 0, abs(leg) * 0.3, leg * 1.2)
    bump("right_knee", 0, 0, -leg)
    bump("right_ankle", 0, abs(leg) * 0.3, -leg * 1.2)
    bump("left_elbow", 0, 0, -arm)
    bump("left_wrist", 0, 0, -arm * 1.5)
    bump("right_elbow", 0, 0, arm)
    bump("right_wrist", 0, 0, arm * 1.5)
    return base


class MockBackend(PoseBackend):
    """Reads JSON fixture sequence or synthesizes idle/walk motion."""

    name = "mock"

    def __init__(
        self,
        fixture_path: Optional[str] = None,
        mode: str = "walk",
        confidence_cfg: Optional[ConfidenceConfig] = None,
    ):
        self.fixture_path = fixture_path
        self.mode = mode
        self._frames: List[Dict[str, Any]] = []
        self._index = 0
        self._hyst = TrackingHysteresis(confidence_cfg or ConfidenceConfig())
        self._ready = False

    def initialize(self, **kwargs: Any) -> bool:
        path = kwargs.get("fixture_path", self.fixture_path)
        mode = kwargs.get("mode", self.mode)
        if path:
            p = Path(path)
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                self._frames = data.get("frames", data if isinstance(data, list) else [])
                self.mode = "fixture"
        else:
            self.mode = mode
        self._index = 0
        self._ready = True
        return True

    def is_available(self) -> bool:
        return True

    def infer(self, frame_bgr: Any = None, frame_index: int = 0, timestamp: float = 0.0) -> PoseFrame:
        if not self._ready:
            self.initialize()

        if self.mode == "fixture" and self._frames:
            raw = self._frames[self._index % len(self._frames)]
            self._index += 1
            landmarks = self._parse_frame(raw)
            t = float(raw.get("timestamp", timestamp))
            fi = int(raw.get("frame_index", frame_index))
        else:
            t = timestamp if timestamp else frame_index / 30.0
            if self.mode == "idle":
                landmarks = _idle_skeleton(t)
            else:
                landmarks = _walking_skeleton(t)
            fi = frame_index

        filtered = self._hyst.filter_landmarks(landmarks)
        state = self._hyst.update(landmarks)
        return PoseFrame(
            landmarks=filtered,
            tracking_state=state,
            timestamp=t if "t" in dir() else timestamp,
            frame_index=fi,
        )

    def _parse_frame(self, raw: Dict[str, Any]) -> Dict[str, Landmark]:
        landmarks: Dict[str, Landmark] = {}
        items = raw.get("landmarks", raw)
        if isinstance(items, dict):
            for name, v in items.items():
                if isinstance(v, dict):
                    pos = v.get("position", v)
                    landmarks[name] = Landmark(
                        name=name,
                        position=Vec3(
                            float(pos.get("x", 0)),
                            float(pos.get("y", 0)),
                            float(pos.get("z", 0)),
                        ),
                        confidence=float(v.get("confidence", 1.0)),
                        valid=True,
                    )
                elif isinstance(v, (list, tuple)) and len(v) >= 3:
                    landmarks[name] = Landmark(
                        name, Vec3(float(v[0]), float(v[1]), float(v[2])),
                        float(v[3]) if len(v) > 3 else 1.0, True,
                    )
        return landmarks

    def shutdown(self) -> None:
        self._ready = False
        self._frames = []

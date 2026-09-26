"""Confidence thresholding and tracking-state hysteresis (FR-022, FR-023)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .types import Landmark, TrackingState


@dataclass
class ConfidenceConfig:
    min_confidence: float = 0.5
    ok_mean_threshold: float = 0.65
    degraded_mean_threshold: float = 0.35
    lost_enter_frames: int = 5
    lost_exit_frames: int = 3
    degraded_enter_frames: int = 3
    degraded_exit_frames: int = 2


@dataclass
class TrackingHysteresis:
    """Stateful tracker that applies hysteresis before changing TrackingState."""

    config: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    state: TrackingState = TrackingState.LOST
    _low_streak: int = 0
    _ok_streak: int = 0
    _degraded_streak: int = 0

    def filter_landmarks(
        self, landmarks: Dict[str, Landmark]
    ) -> Dict[str, Landmark]:
        out: Dict[str, Landmark] = {}
        thr = self.config.min_confidence
        for name, lm in landmarks.items():
            valid = lm.confidence >= thr and lm.valid
            out[name] = Landmark(
                name=lm.name,
                position=lm.position,
                confidence=lm.confidence,
                valid=valid,
            )
        return out

    def mean_confidence(self, landmarks: Dict[str, Landmark]) -> float:
        if not landmarks:
            return 0.0
        vals = [lm.confidence for lm in landmarks.values()]
        return sum(vals) / len(vals)

    def valid_ratio(self, landmarks: Dict[str, Landmark]) -> float:
        if not landmarks:
            return 0.0
        valid = sum(1 for lm in landmarks.values() if lm.valid)
        return valid / len(landmarks)

    def update(self, landmarks: Dict[str, Landmark]) -> TrackingState:
        filtered = self.filter_landmarks(landmarks)
        mean_c = self.mean_confidence(filtered)
        ratio = self.valid_ratio(filtered)
        cfg = self.config

        if mean_c >= cfg.ok_mean_threshold and ratio >= 0.6:
            raw = TrackingState.OK
        elif mean_c >= cfg.degraded_mean_threshold and ratio >= 0.3:
            raw = TrackingState.DEGRADED
        else:
            raw = TrackingState.LOST

        if raw == TrackingState.OK:
            self._ok_streak += 1
            self._low_streak = 0
            self._degraded_streak = 0
            if self.state == TrackingState.LOST:
                if self._ok_streak >= cfg.lost_exit_frames:
                    self.state = TrackingState.OK
            elif self.state == TrackingState.DEGRADED:
                if self._ok_streak >= cfg.degraded_exit_frames:
                    self.state = TrackingState.OK
            else:
                self.state = TrackingState.OK
        elif raw == TrackingState.DEGRADED:
            self._degraded_streak += 1
            self._ok_streak = 0
            self._low_streak = 0
            if self.state == TrackingState.OK:
                if self._degraded_streak >= cfg.degraded_enter_frames:
                    self.state = TrackingState.DEGRADED
            elif self.state == TrackingState.LOST:
                if self._degraded_streak >= cfg.lost_exit_frames:
                    self.state = TrackingState.DEGRADED
            else:
                self.state = TrackingState.DEGRADED
        else:
            self._low_streak += 1
            self._ok_streak = 0
            self._degraded_streak = 0
            if self.state != TrackingState.LOST:
                if self._low_streak >= cfg.lost_enter_frames:
                    self.state = TrackingState.LOST
            else:
                self.state = TrackingState.LOST

        return self.state


class HoldInterpolatePolicy:
    """Hold-last or brief interpolate when tracking degrades (FR-023)."""

    def __init__(self, mode: str = "hold_last", max_interp_frames: int = 5):
        self.mode = mode  # hold_last | interpolate | drop
        self.max_interp_frames = max_interp_frames
        self._last_valid: Optional[Dict[str, Landmark]] = None
        self._gap_frames: int = 0

    def process(
        self,
        landmarks: Dict[str, Landmark],
        state: TrackingState,
    ) -> Optional[Dict[str, Landmark]]:
        has_valid = any(lm.valid for lm in landmarks.values())
        if state == TrackingState.OK or (
            state == TrackingState.DEGRADED and has_valid
        ):
            self._last_valid = landmarks
            self._gap_frames = 0
            return landmarks

        self._gap_frames += 1
        if self.mode == "drop":
            return None
        if self.mode == "hold_last":
            return self._last_valid
        # interpolate: for offline we hold last (full interp needs two anchors)
        if self._gap_frames <= self.max_interp_frames:
            return self._last_valid
        return None

"""Temporal smoothing of landmark positions (pure Python, optional FR-064 filter)."""

from __future__ import annotations

from typing import Dict, Optional

from .types import Landmark, Vec3


class LandmarkSmoother:
    """Exponential moving average per landmark.

    ``strength`` 0 disables smoothing; 1 would freeze the pose. Invalid landmarks
    are passed through untouched and reset their history so a re-acquired joint
    does not swing in from a stale position.
    """

    def __init__(self, strength: float = 0.0):
        self.strength = strength
        self._state: Dict[str, Vec3] = {}

    def reset(self) -> None:
        self._state.clear()

    def process(self, landmarks: Optional[Dict[str, Landmark]]) -> Optional[Dict[str, Landmark]]:
        if landmarks is None:
            return None
        alpha = 1.0 - max(0.0, min(0.95, self.strength))
        if alpha >= 1.0:
            return landmarks
        out: Dict[str, Landmark] = {}
        for name, lm in landmarks.items():
            if not lm.valid:
                self._state.pop(name, None)
                out[name] = lm
                continue
            prev = self._state.get(name)
            pos = lm.position if prev is None else prev + (lm.position - prev) * alpha
            self._state[name] = pos
            out[name] = Landmark(lm.name, pos, lm.confidence, True)
        return out

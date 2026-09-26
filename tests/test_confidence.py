"""Confidence thresholding and tracking hysteresis tests (FR-022–023)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bodymocap.core.confidence import (
    ConfidenceConfig,
    HoldInterpolatePolicy,
    TrackingHysteresis,
)
from bodymocap.core.types import Landmark, TrackingState, Vec3


def _lms(conf: float, n: int = 10) -> dict:
    return {
        f"j{i}": Landmark(f"j{i}", Vec3(0, float(i), 0), conf, True)
        for i in range(n)
    }


class TestConfidence(unittest.TestCase):
    def test_filter_below_threshold(self):
        cfg = ConfidenceConfig(min_confidence=0.5)
        h = TrackingHysteresis(cfg)
        filtered = h.filter_landmarks(_lms(0.3))
        self.assertTrue(all(not lm.valid for lm in filtered.values()))

    def test_hysteresis_enter_lost(self):
        cfg = ConfidenceConfig(
            min_confidence=0.5,
            ok_mean_threshold=0.65,
            degraded_mean_threshold=0.35,
            lost_enter_frames=3,
            lost_exit_frames=2,
            degraded_enter_frames=2,
            degraded_exit_frames=2,
        )
        h = TrackingHysteresis(cfg)
        # Leave initial LOST (needs lost_exit_frames of OK)
        for _ in range(cfg.lost_exit_frames):
            h.update(_lms(0.9))
        self.assertEqual(h.state, TrackingState.OK)
        # Drop to lost — need lost_enter_frames
        states = [h.update(_lms(0.1)) for _ in range(5)]
        self.assertEqual(states[0], TrackingState.OK)  # hysteresis hold
        self.assertEqual(states[1], TrackingState.OK)
        self.assertEqual(states[2], TrackingState.LOST)

    def test_hysteresis_recover(self):
        cfg = ConfidenceConfig(
            lost_enter_frames=2,
            lost_exit_frames=3,
            degraded_enter_frames=2,
            degraded_exit_frames=2,
            ok_mean_threshold=0.65,
            degraded_mean_threshold=0.35,
        )
        h = TrackingHysteresis(cfg)
        h.state = TrackingState.LOST
        # Need lost_exit_frames of OK to leave LOST
        s1 = h.update(_lms(0.9))
        s2 = h.update(_lms(0.9))
        s3 = h.update(_lms(0.9))
        self.assertEqual(s1, TrackingState.LOST)
        self.assertEqual(s2, TrackingState.LOST)
        self.assertEqual(s3, TrackingState.OK)

    def test_hold_last_policy(self):
        policy = HoldInterpolatePolicy(mode="hold_last")
        good = _lms(0.9)
        out = policy.process(good, TrackingState.OK)
        self.assertIsNotNone(out)
        held = policy.process(_lms(0.1), TrackingState.LOST)
        self.assertIs(held, good)

    def test_drop_policy(self):
        policy = HoldInterpolatePolicy(mode="drop")
        policy.process(_lms(0.9), TrackingState.OK)
        out = policy.process(_lms(0.1), TrackingState.LOST)
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()

"""Recording session: real-time frame indexing, pauses and de-duplication."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bodymocap.core.smoothing import LandmarkSmoother  # noqa: E402
from bodymocap.core.types import Landmark, Quat, TrackingState, Vec3  # noqa: E402
from bodymocap.recording.session import RecordingSession  # noqa: E402


class SessionTimingTests(unittest.TestCase):
    def test_frame_index_follows_wall_clock_at_scene_fps(self):
        s = RecordingSession()
        s.start(fps=24.0, timestamp=100.0)
        for t in (100.0, 100.5, 101.0):
            s.append(bone_rotations={"Hips": Quat()}, timestamp=t)
        self.assertEqual([f.frame_index for f in s.frames], [0, 12, 24])
        self.assertAlmostEqual(s.duration_seconds(), 25 / 24)

    def test_samples_on_the_same_frame_replace_each_other(self):
        s = RecordingSession()
        s.start(fps=24.0, timestamp=0.0)
        s.append(bone_rotations={"Hips": Quat(1, 0, 0, 0)}, timestamp=0.50)
        s.append(bone_rotations={"Hips": Quat(0, 1, 0, 0)}, timestamp=0.51)
        self.assertEqual(s.frame_count(), 1)
        self.assertEqual(s.frames[0].bone_rotations["Hips"], Quat(0, 1, 0, 0))

    def test_pause_time_is_removed(self):
        s = RecordingSession()
        s.start(fps=24.0, timestamp=100.0)
        s.append(bone_rotations={}, timestamp=101.0)
        s.pause(timestamp=101.0)
        self.assertIsNone(s.append(bone_rotations={}, timestamp=102.0))
        s.resume(timestamp=103.0)
        s.append(bone_rotations={}, timestamp=103.5)
        self.assertEqual([f.frame_index for f in s.frames], [24, 36])

    def test_explicit_indices_and_locations_are_kept(self):
        s = RecordingSession()
        s.start(fps=30.0, timestamp=0.0)
        s.append(5, {"Hips": Quat()}, TrackingState.DEGRADED, 0.0, {"Hips": Vec3(0, 0, 1)})
        self.assertEqual(s.frames[0].frame_index, 5)
        self.assertEqual(s.frames[0].bone_locations["Hips"], Vec3(0, 0, 1))
        self.assertEqual(s.degraded_or_lost_fraction(), 1.0)
        self.assertIn("bone_locations", s.to_serializable()["frames"][0])


class SmootherTests(unittest.TestCase):
    def test_zero_strength_passes_through(self):
        sm = LandmarkSmoother(0.0)
        lms = {"nose": Landmark("nose", Vec3(1, 2, 3))}
        self.assertIs(sm.process(lms), lms)

    def test_smoothing_moves_toward_new_position_and_resets_on_invalid(self):
        sm = LandmarkSmoother(0.5)
        sm.process({"nose": Landmark("nose", Vec3(0, 0, 0))})
        out = sm.process({"nose": Landmark("nose", Vec3(1, 0, 0))})
        self.assertAlmostEqual(out["nose"].position.x, 0.5)
        sm.process({"nose": Landmark("nose", Vec3(5, 0, 0), 0.1, False)})
        out = sm.process({"nose": Landmark("nose", Vec3(2, 0, 0))})
        self.assertAlmostEqual(out["nose"].position.x, 2.0)


if __name__ == "__main__":
    unittest.main()

"""Pure-Python tests for the 3D pose solver targets, calibration and root motion."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bodymocap.core.math3d import frame_quat, quat_angle_deg, quat_rotate  # noqa: E402
from bodymocap.core.types import Landmark, Quat, Vec3  # noqa: E402
from bodymocap.mapping.apply_pose import (  # noqa: E402
    apply_landmarks_to_rotations,
    average_calibrations,
    build_calibration_from_landmarks,
    build_root_reference,
    compute_pose_targets,
    root_offset_metres,
    to_blender_quat,
    to_blender_vec,
)

# Metric T-pose, hip-centred, backend coords (x = subject's left, y up, z toward camera)
T_POSE = {
    "nose": (0.0, 0.65, 0.08),
    "left_eye": (0.03, 0.68, 0.06),
    "right_eye": (-0.03, 0.68, 0.06),
    "left_ear": (0.07, 0.66, 0.0),
    "right_ear": (-0.07, 0.66, 0.0),
    "left_shoulder": (0.2, 0.5, 0.0),
    "right_shoulder": (-0.2, 0.5, 0.0),
    "left_elbow": (0.48, 0.5, 0.0),
    "right_elbow": (-0.48, 0.5, 0.0),
    "left_wrist": (0.75, 0.5, 0.0),
    "right_wrist": (-0.75, 0.5, 0.0),
    "left_index": (0.83, 0.5, 0.0),
    "right_index": (-0.83, 0.5, 0.0),
    "left_hip": (0.1, 0.0, 0.0),
    "right_hip": (-0.1, 0.0, 0.0),
    "left_knee": (0.1, -0.45, 0.0),
    "right_knee": (-0.1, -0.45, 0.0),
    "left_ankle": (0.1, -0.9, 0.0),
    "right_ankle": (-0.1, -0.9, 0.0),
    "left_foot_index": (0.1, -0.95, 0.15),
    "right_foot_index": (-0.1, -0.95, 0.15),
}

ROLE_MAP = {
    "hips": "Hips",
    "spine": "Spine",
    "head": "Head",
    "upper_arm_L": "UpperArm.L",
    "forearm_L": "Forearm.L",
    "thigh_R": "Thigh.R",
}


def landmarks(points=T_POSE, rotation: Quat = None, offset: Vec3 = None):
    out = {}
    for name, (x, y, z) in points.items():
        p = Vec3(x, y, z)
        if rotation is not None:
            p = quat_rotate(rotation, p)
        if offset is not None:
            p = p + offset
        out[name] = Landmark(name, p, 0.95, True)
    return out


def image_landmarks(points=T_POSE, scale=0.25, shift=(0.0, 0.5)):
    """Fake projection: metres → normalized image (x centred, y up)."""
    return {
        name: Landmark(name, Vec3(x * scale + shift[0], y * scale + shift[1], 0.0), 0.95, True)
        for name, (x, y, z) in points.items()
    }


def yaw(deg: float) -> Quat:
    h = math.radians(deg) * 0.5
    return Quat(math.cos(h), 0.0, math.sin(h), 0.0)  # about backend up axis


def pitch(deg: float) -> Quat:
    h = math.radians(deg) * 0.5
    return Quat(math.cos(h), math.sin(h), 0.0, 0.0)  # about backend x axis


def assert_vec_close(test, v: Vec3, expected, tol=1e-3):
    for got, want in zip(v.as_tuple(), expected):
        test.assertAlmostEqual(got, want, delta=tol, msg=f"{v.as_tuple()} != {expected}")


class FrameMathTests(unittest.TestCase):
    def test_canonical_frame_is_identity(self):
        q = frame_quat(Vec3(1, 0, 0), Vec3(0, 1, 0))
        self.assertLess(quat_angle_deg(q, Quat()), 1e-6)

    def test_turned_left_is_yaw_about_up(self):
        # Subject turned 90° to their left: their left side now points away from the camera
        q = frame_quat(Vec3(0, 0, -1), Vec3(0, 1, 0))
        self.assertLess(quat_angle_deg(q, yaw(90)), 1e-4)

    def test_to_blender_quat_turns_yaw_into_z_rotation(self):
        q = to_blender_quat(yaw(90))
        expected = Quat(math.cos(math.radians(45)), 0.0, 0.0, math.sin(math.radians(45)))
        self.assertLess(quat_angle_deg(q, expected), 1e-4)
        # and vectors follow the same convention
        assert_vec_close(self, to_blender_vec(Vec3(0, 1, 0)), (0, 0, 1))
        assert_vec_close(self, to_blender_vec(Vec3(0, 0, 1)), (0, -1, 0))


class PoseTargetTests(unittest.TestCase):
    def test_tpose_without_calibration_matches_canonical_rig(self):
        targets = compute_pose_targets(landmarks(), ROLE_MAP)
        assert_vec_close(self, targets.directions["UpperArm.L"], (1, 0, 0))
        assert_vec_close(self, targets.directions["Forearm.L"], (1, 0, 0))
        assert_vec_close(self, targets.directions["Thigh.R"], (0, 0, -1))
        for bone in ("Hips", "Spine", "Head"):
            self.assertLess(quat_angle_deg(targets.frame_deltas[bone], Quat()), 1e-3, bone)

    def test_turning_the_body_yaws_hips_in_3d(self):
        targets = compute_pose_targets(landmarks(rotation=yaw(60)), ROLE_MAP)
        expected = to_blender_quat(yaw(60))
        self.assertLess(quat_angle_deg(targets.frame_deltas["Hips"], expected), 0.5)
        # The arm direction turned with the body (no longer on the camera plane)
        arm = targets.directions["UpperArm.L"]
        self.assertGreater(abs(arm.y), 0.8)

    def test_head_turn_is_independent_of_torso(self):
        pts = dict(T_POSE)
        head_q = yaw(-45)
        for name in ("nose", "left_eye", "right_eye", "left_ear", "right_ear"):
            x, y, z = pts[name]
            p = Vec3(x, y - 0.55, z)  # rotate about the neck (shoulders_mid height ~0.5)
            p = quat_rotate(head_q, p)
            pts[name] = (p.x, p.y + 0.55, p.z)
        targets = compute_pose_targets(landmarks(pts), ROLE_MAP)
        self.assertLess(quat_angle_deg(targets.frame_deltas["Hips"], Quat()), 1e-3)
        self.assertLess(quat_angle_deg(targets.frame_deltas["Head"], to_blender_quat(head_q)), 1.0)

    def test_pitching_forward_is_a_3d_rotation_not_a_2d_shrink(self):
        targets = compute_pose_targets(landmarks(rotation=pitch(-40)), ROLE_MAP)
        expected = to_blender_quat(pitch(-40))
        self.assertLess(quat_angle_deg(targets.frame_deltas["Spine"], expected), 0.5)

    def test_apply_without_armature_returns_all_mapped_bones(self):
        rots = apply_landmarks_to_rotations(landmarks(), ROLE_MAP)
        self.assertEqual(set(rots), set(ROLE_MAP.values()))


class CalibrationTests(unittest.TestCase):
    def test_calibration_removes_camera_tilt_and_stance_yaw(self):
        tilt = quat_rotate  # noqa: F841 (readability)
        camera_pose = yaw(25)
        # Compose a pitch (camera looking up at the subject) with the yaw
        from bodymocap.core.math3d import quat_mul

        camera_pose = quat_mul(pitch(15), camera_pose)
        seen = landmarks(rotation=camera_pose)
        cal = build_calibration_from_landmarks(seen)
        self.assertTrue(cal.valid)
        targets = compute_pose_targets(seen, ROLE_MAP, cal)
        # After correction the same pose reads as the canonical T-pose
        assert_vec_close(self, targets.directions["UpperArm.L"], (1, 0, 0), tol=1e-2)
        for bone in ("Hips", "Spine", "Head"):
            self.assertLess(quat_angle_deg(targets.frame_deltas[bone], Quat()), 0.5, bone)
        # Turning 90° relative to the calibration pose reads as 90° in Blender Z
        from bodymocap.core.math3d import quat_mul as mul

        turned = landmarks(rotation=mul(camera_pose, yaw(90)))
        targets = compute_pose_targets(turned, ROLE_MAP, cal)
        self.assertLess(quat_angle_deg(targets.frame_deltas["Hips"], to_blender_quat(yaw(90))), 1.0)

    def test_average_calibrations_accepts_landmark_lists(self):
        cal = average_calibrations([landmarks(), landmarks()])
        self.assertTrue(cal.valid)
        self.assertAlmostEqual(cal.torso_length, 0.5, places=6)
        self.assertIn("hips", cal.role_frames)

    def test_rest_pose_after_calibration_is_rest_on_a_tilted_rig_frame(self):
        # A performer whose spine leans 10° at rest: calibration makes that the zero pose
        leaning = landmarks(rotation=pitch(10))
        cal = build_calibration_from_landmarks(leaning)
        targets = compute_pose_targets(leaning, ROLE_MAP, cal)
        self.assertLess(quat_angle_deg(targets.frame_deltas["Spine"], Quat()), 1e-3)


class RootMotionTests(unittest.TestCase):
    def test_reference_and_offsets(self):
        world = landmarks()
        img = image_landmarks()
        ref = build_root_reference(img, world, aspect=1.0, distance=2.0)
        self.assertTrue(ref.valid)
        self.assertAlmostEqual(ref.metres_per_unit, 4.0, places=5)  # 0.25 image units per metre

        # No movement → zero offset
        assert_vec_close(self, root_offset_metres(img, world, ref, 1.0), (0, 0, 0), tol=1e-6)

        # Step 0.1 image units to the left (subject's left = +x) → 0.4 m
        moved = image_landmarks(shift=(0.1, 0.5))
        assert_vec_close(self, root_offset_metres(moved, world, ref, 1.0), (0.4, 0, 0), tol=1e-6)

        # Appear half as big → twice as far: depth 4 m, i.e. 2 m further away (−z)
        far = image_landmarks(scale=0.125, shift=(0.0, 0.5))
        offset = root_offset_metres(far, world, ref, 1.0)
        self.assertAlmostEqual(offset.z, -2.0, places=5)

    def test_pose_targets_include_root_offset_in_blender_space(self):
        world = landmarks()
        ref = build_root_reference(image_landmarks(), world, 1.0, 2.0)
        far = image_landmarks(scale=0.125)
        targets = compute_pose_targets(world, ROLE_MAP, None, image_landmarks=far, aspect=1.0, root_reference=ref)
        self.assertIsNotNone(targets.root_offset_m)
        # Further from the camera = +Y in Blender (behind a rig that faces -Y)
        self.assertAlmostEqual(targets.root_offset_m.y, 2.0, places=5)


if __name__ == "__main__":
    unittest.main()

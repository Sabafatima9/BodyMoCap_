"""Unit tests for core math3d."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bodymocap.core.math3d import (
    quat_average,
    quat_from_two_vectors,
    quat_identity,
    quat_mul,
    quat_normalize,
    quat_slerp,
    vec_lerp,
)
from bodymocap.core.types import Quat, Vec3


class TestMath3d(unittest.TestCase):
    def test_identity_mul(self):
        q = Quat(0.7071, 0.7071, 0, 0)
        r = quat_mul(quat_identity(), q)
        self.assertAlmostEqual(r.w, q.w, places=3)

    def test_from_two_vectors_same(self):
        q = quat_from_two_vectors(Vec3(0, 1, 0), Vec3(0, 1, 0))
        self.assertAlmostEqual(q.w, 1.0, places=5)

    def test_from_two_vectors_90(self):
        q = quat_from_two_vectors(Vec3(1, 0, 0), Vec3(0, 1, 0))
        q = quat_normalize(q)
        # 90 deg around Z
        self.assertAlmostEqual(abs(q.w), math.sqrt(0.5), places=3)

    def test_slerp_midpoint(self):
        a = quat_identity()
        b = quat_from_two_vectors(Vec3(1, 0, 0), Vec3(0, 1, 0))
        m = quat_slerp(a, b, 0.5)
        self.assertTrue(0.5 < m.w < 1.0)

    def test_quat_average(self):
        a = quat_identity()
        b = quat_identity()
        avg = quat_average([a, b])
        self.assertAlmostEqual(avg.w, 1.0, places=5)

    def test_vec_lerp(self):
        v = vec_lerp(Vec3(0, 0, 0), Vec3(2, 0, 0), 0.5)
        self.assertAlmostEqual(v.x, 1.0)


if __name__ == "__main__":
    unittest.main()

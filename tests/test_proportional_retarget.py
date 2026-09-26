"""Unit tests for N:M proportional remapping (FR-072–074)."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bodymocap.core.math3d import (
    cumulative_quat_product,
    euler_xyz_to_quat,
    quat_angle_deg,
    quat_identity,
    quat_normalize,
)
from bodymocap.core.types import Quat
from bodymocap.retarget.proportional import (
    aggregate_rotations,
    assign_source_intervals_to_targets,
    example_arm_2_to_4,
    example_arm_4_to_2,
    remap_chain,
    split_rotations,
)


def _rx(degrees: float) -> Quat:
    return euler_xyz_to_quat(math.radians(degrees), 0.0, 0.0)


class TestProportionalRetarget(unittest.TestCase):
    def test_intervals_4_to_2_equal(self):
        intervals = assign_source_intervals_to_targets(
            [1, 1, 1, 1], [2, 2]
        )
        self.assertEqual(len(intervals), 2)
        # Cover all 4 segments without gaps
        self.assertEqual(intervals[0][0], 0)
        self.assertEqual(intervals[-1][1], 4)
        self.assertEqual(intervals[0][1], intervals[1][0])

    def test_aggregate_4_to_2(self):
        # Four small bends → two bones
        src = [_rx(10), _rx(10), _rx(15), _rx(15)]
        out = example_arm_4_to_2(src, [1, 1, 1, 1], [2, 2])
        self.assertEqual(len(out), 2)
        # Proximal aggregate ≈ 20°, distal ≈ 30° (cumulative)
        proximal = cumulative_quat_product([_rx(10), _rx(10)])
        distal = cumulative_quat_product([_rx(15), _rx(15)])
        self.assertLess(quat_angle_deg(out[0], proximal), 1.0)
        self.assertLess(quat_angle_deg(out[1], distal), 1.0)

    def test_split_2_to_4(self):
        src = [_rx(20), _rx(40)]
        out = example_arm_2_to_4(src, [2, 2], [1, 1, 1, 1])
        self.assertEqual(len(out), 4)
        # Total chain product should approximate source product
        src_total = cumulative_quat_product(src)
        out_total = cumulative_quat_product(out)
        self.assertLess(quat_angle_deg(src_total, out_total), 2.0)

    def test_remap_dispatch(self):
        src4 = [_rx(5), _rx(5), _rx(5), _rx(5)]
        a = remap_chain(src4, [1, 1, 1, 1], [2, 2])
        self.assertEqual(len(a), 2)
        src2 = [_rx(10), _rx(10)]
        b = remap_chain(src2, [2, 2], [1, 1, 1, 1])
        self.assertEqual(len(b), 4)

    def test_equal_n_m(self):
        src = [_rx(12), _rx(8), _rx(4)]
        out = remap_chain(src, [1, 1, 1], [1, 1, 1])
        self.assertEqual(len(out), 3)
        for a, b in zip(src, out):
            self.assertLess(quat_angle_deg(a, b), 0.01)

    def test_unequal_lengths_4_to_2(self):
        src = [_rx(10), _rx(10), _rx(10), _rx(10)]
        # Longer proximal target bone should absorb more source segments
        out = aggregate_rotations(src, [1, 1, 1, 1], [3, 1])
        self.assertEqual(len(out), 2)
        intervals = assign_source_intervals_to_targets([1, 1, 1, 1], [3, 1])
        self.assertGreaterEqual(intervals[0][1] - intervals[0][0], intervals[1][1] - intervals[1][0])


if __name__ == "__main__":
    unittest.main()

"""Apply landmarks → pose bone rotations with calibration (FR-043–044).

FK approach: for each mapped bone, compute world direction from parent landmark
to child landmark, convert to rotation relative to calibrated rest direction.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from ..core.landmarks import ROLE_LANDMARK_PAIRS
from ..core.math3d import (
    direction_from_landmarks,
    quat_from_two_vectors,
    quat_identity,
    quat_mul,
    quat_normalize,
    quat_conjugate,
)
from ..core.types import CalibrationData, Landmark, Quat, Vec3


def _mid(a: Optional[Landmark], b: Optional[Landmark]) -> Optional[Vec3]:
    if a is None or b is None:
        return None
    if not a.valid or not b.valid:
        return None
    return Vec3(
        0.5 * (a.position.x + b.position.x),
        0.5 * (a.position.y + b.position.y),
        0.5 * (a.position.z + b.position.z),
    )


def resolve_landmark_position(
    name: str,
    landmarks: Dict[str, Landmark],
) -> Optional[Vec3]:
    if name == "hips_mid":
        return _mid(landmarks.get("left_hip"), landmarks.get("right_hip"))
    if name == "shoulders_mid":
        return _mid(landmarks.get("left_shoulder"), landmarks.get("right_shoulder"))
    lm = landmarks.get(name)
    if lm is None or not lm.valid:
        return None
    return lm.position


def bone_direction_from_landmarks(
    role: str,
    landmarks: Dict[str, Landmark],
) -> Optional[Vec3]:
    pair = ROLE_LANDMARK_PAIRS.get(role)
    if not pair:
        return None
    parent_name, child_name = pair
    # Special case hips: use left→right as lateral, derive facing separately
    if role == "hips":
        lh = landmarks.get("left_hip")
        rh = landmarks.get("right_hip")
        if not lh or not rh or not lh.valid or not rh.valid:
            return None
        # Up from mid-hip toward mid-shoulder as "spine-ish"; for hips use
        # average leg-up or shoulder-up. Use hips_mid → shoulders_mid for facing plane.
        mid_h = resolve_landmark_position("hips_mid", landmarks)
        mid_s = resolve_landmark_position("shoulders_mid", landmarks)
        if mid_h and mid_s:
            return direction_from_landmarks(mid_h, mid_s)
        return direction_from_landmarks(rh.position, lh.position)

    p = resolve_landmark_position(parent_name, landmarks)
    c = resolve_landmark_position(child_name, landmarks)
    if p is None or c is None:
        return None
    return direction_from_landmarks(p, c)


def compute_bone_delta(
    current_dir: Vec3,
    rest_dir: Vec3,
) -> Quat:
    """Rotation taking rest_dir to current_dir (pose delta)."""
    return quat_from_two_vectors(rest_dir, current_dir)


def build_calibration_from_landmarks(
    landmarks: Dict[str, Landmark],
    roles: Optional[list] = None,
) -> CalibrationData:
    """Average single-frame capture into CalibrationData (caller averages over time)."""
    roles = roles or list(ROLE_LANDMARK_PAIRS.keys())
    cal = CalibrationData(valid=True)
    for name, lm in landmarks.items():
        if lm.valid:
            cal.average_landmarks[name] = lm.position
    for role in roles:
        d = bone_direction_from_landmarks(role, landmarks)
        if d is not None and d.length() > 1e-6:
            cal.bone_rest_dirs[role] = d
    # Scale from hip–shoulder distance
    mid_h = resolve_landmark_position("hips_mid", landmarks)
    mid_s = resolve_landmark_position("shoulders_mid", landmarks)
    if mid_h and mid_s:
        cal.scale = (mid_s - mid_h).length() or 1.0
    return cal


def average_calibrations(samples: list) -> CalibrationData:
    """Average multiple CalibrationData / landmark dicts."""
    if not samples:
        return CalibrationData(valid=False)
    # samples are Dict[str, Landmark] frames
    from collections import defaultdict

    sums: Dict[str, Vec3] = defaultdict(lambda: Vec3(0, 0, 0))
    counts: Dict[str, int] = defaultdict(int)
    for landmarks in samples:
        for name, lm in landmarks.items():
            if isinstance(lm, Landmark):
                if not lm.valid:
                    continue
                pos = lm.position
            else:
                pos = lm
            sums[name] = sums[name] + pos
            counts[name] += 1
    avg_lms: Dict[str, Landmark] = {}
    for name, s in sums.items():
        c = counts[name]
        avg_lms[name] = Landmark(name, Vec3(s.x / c, s.y / c, s.z / c), 1.0, True)
    return build_calibration_from_landmarks(avg_lms)


def apply_landmarks_to_rotations(
    landmarks: Dict[str, Landmark],
    role_to_bone: Dict[str, str],
    calibration: Optional[CalibrationData] = None,
) -> Dict[str, Quat]:
    """Return bone_name → delta quaternion for mapped roles."""
    result: Dict[str, Quat] = {}
    for role, bone_name in role_to_bone.items():
        if not bone_name:
            continue
        cur = bone_direction_from_landmarks(role, landmarks)
        if cur is None:
            continue
        if calibration and calibration.valid and role in calibration.bone_rest_dirs:
            rest = calibration.bone_rest_dirs[role]
            delta = compute_bone_delta(cur, rest)
        else:
            # Without calibration, rotate from default up
            rest = Vec3(0, 1, 0)
            delta = compute_bone_delta(cur, rest)
        result[bone_name] = quat_normalize(delta)
    return result


def apply_rotations_to_armature(
    armature_obj,
    bone_rotations: Dict[str, Quat],
) -> int:
    """Write quaternions onto pose bones. Returns count applied. Requires bpy."""
    try:
        from mathutils import Quaternion
    except ImportError:
        return 0
    count = 0
    for bone_name, q in bone_rotations.items():
        pb = armature_obj.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion((q.w, q.x, q.y, q.z))
        count += 1
    return count

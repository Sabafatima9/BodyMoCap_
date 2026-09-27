"""Apply landmarks → pose bone rotations (+ root translation) with calibration (FR-043–044).

Per frame:

1. **World correction** – rotate the metric landmarks by
   ``calibration.world_correction`` so the subject is upright and faces the camera
   regardless of camera tilt or the stance yaw held during calibration.
2. **Limb directions (absolute)** – each mapped limb role gets the world direction
   from its parent landmark to its child landmark; the rig bone is pointed exactly
   that way. No rest-pose assumptions, so an A-pose rig follows a T-pose performer.
3. **Body frames** – hips / spine / chest / neck / head use a full orientation frame
   (lateral + up) so turning, bending, twisting and head yaw carry into the rig as
   3D rotations instead of collapsing onto the camera plane. Frames are measured
   relative to the calibrated (or canonical) frame, which keeps rigs whose torso
   bones are tilted in rest at rest when the performer is at rest (FR-044).
4. **Root translation** – hip position on the image plus apparent body size give
   left/right, up/down and towards/away movement in metres.
5. **Armature solve** – top-down: each bone starts where it would be if it rigidly
   followed its parent ("follow"), then swings to its target. Local rotation is
   ``follow⁻¹ · target`` so twist is inherited from the parent and the whole body
   rotates coherently.

Coordinates: backend space is x = subject's left (image right), y = up,
z = toward the camera. Blender world is obtained with (x, -z, y).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..core.landmarks import ROLE_LANDMARK_PAIRS
from ..core.math3d import (
    direction_from_landmarks,
    frame_quat,
    orthonormal_frame,
    quat_conjugate,
    quat_from_two_vectors,
    quat_identity,
    quat_mul,
    quat_normalize,
    quat_rotate,
)
from ..core.types import (
    CalibrationData,
    Frame3,
    Landmark,
    PoseSolution,
    Quat,
    RootReference,
    Vec3,
)

# Roles solved as full orientation frames: role → (lateral from, lateral to, up from, up to)
# ``lateral`` points to the subject's left; ``up`` along the bone.
ROLE_FRAME_SPEC: Dict[str, Tuple[str, str, str, str]] = {
    "hips": ("right_hip", "left_hip", "hips_mid", "shoulders_mid"),
    "spine": ("right_shoulder", "left_shoulder", "hips_mid", "shoulders_mid"),
    "chest": ("right_shoulder", "left_shoulder", "hips_mid", "shoulders_mid"),
    "neck": ("right_shoulder", "left_shoulder", "shoulders_mid", "ears_mid"),
    "head": ("right_ear", "left_ear", "shoulders_mid", "ears_mid"),
}

# Fallbacks when the primary lateral landmarks are missing (e.g. one ear hidden)
_LATERAL_FALLBACKS: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("right_ear", "left_ear"): ("right_eye", "left_eye"),
    ("right_hip", "left_hip"): ("right_shoulder", "left_shoulder"),
}

# Segments used to estimate apparent body size (metres per image unit)
_SIZE_SEGMENTS: Tuple[Tuple[str, str], ...] = (
    ("hips_mid", "shoulders_mid"),
    ("left_shoulder", "right_shoulder"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("right_hip", "right_knee"),
    ("left_knee", "left_ankle"),
    ("right_knee", "right_ankle"),
    ("left_shoulder", "left_elbow"),
    ("right_shoulder", "right_elbow"),
)

_MID_POINTS: Dict[str, Tuple[str, str]] = {
    "hips_mid": ("left_hip", "right_hip"),
    "shoulders_mid": ("left_shoulder", "right_shoulder"),
    "ears_mid": ("left_ear", "right_ear"),
    "eyes_mid": ("left_eye", "right_eye"),
    "mouth_mid": ("mouth_left", "mouth_right"),
}

# Backend → Blender basis change is a +90° rotation about X: (x, y, z) → (x, -z, y)
_SQRT_HALF = 0.7071067811865476
_TO_BLENDER = Quat(_SQRT_HALF, _SQRT_HALF, 0.0, 0.0)


def to_blender_vec(v: Vec3) -> Vec3:
    return Vec3(v.x, -v.z, v.y)


def to_blender_quat(q: Quat) -> Quat:
    """Express a rotation given in backend coordinates in Blender coordinates."""
    return quat_normalize(quat_mul(quat_mul(_TO_BLENDER, q), quat_conjugate(_TO_BLENDER)))


def _mid(a: Optional[Landmark], b: Optional[Landmark]) -> Optional[Vec3]:
    if a is None or b is None or not a.valid or not b.valid:
        return None
    return (a.position + b.position) * 0.5


def resolve_landmark_position(name: str, landmarks: Dict[str, Landmark]) -> Optional[Vec3]:
    pair = _MID_POINTS.get(name)
    if pair:
        return _mid(landmarks.get(pair[0]), landmarks.get(pair[1]))
    lm = landmarks.get(name)
    if lm is None or not lm.valid:
        return None
    return lm.position


def _direction(parent: str, child: str, landmarks: Dict[str, Landmark]) -> Optional[Vec3]:
    p = resolve_landmark_position(parent, landmarks)
    c = resolve_landmark_position(child, landmarks)
    if p is None or c is None:
        return None
    d = direction_from_landmarks(p, c)
    return d if d.length() > 1e-6 else None


def bone_direction_from_landmarks(role: str, landmarks: Dict[str, Landmark]) -> Optional[Vec3]:
    """Unit direction along the bone for ``role`` (hips/torso: hips_mid → shoulders_mid)."""
    if role in ROLE_FRAME_SPEC:
        _, _, up_from, up_to = ROLE_FRAME_SPEC[role]
        return _direction(up_from, up_to, landmarks)
    pair = ROLE_LANDMARK_PAIRS.get(role)
    if not pair:
        return None
    return _direction(pair[0], pair[1], landmarks)


def body_frame_from_landmarks(role: str, landmarks: Dict[str, Landmark]) -> Optional[Frame3]:
    """Orthonormal (lateral, up, forward) frame for a torso/head role, or None."""
    spec = ROLE_FRAME_SPEC.get(role)
    if spec is None:
        return None
    lat_from, lat_to, up_from, up_to = spec
    up = _direction(up_from, up_to, landmarks)
    lateral = _direction(lat_from, lat_to, landmarks)
    if lateral is None:
        fallback = _LATERAL_FALLBACKS.get((lat_from, lat_to))
        if fallback:
            lateral = _direction(fallback[0], fallback[1], landmarks)
    if up is None or lateral is None:
        return None
    x, y, z = orthonormal_frame(lateral, up)
    return Frame3(x, y, z)


def frame_to_quat(frame: Frame3) -> Quat:
    return frame_quat(frame.lateral, frame.up)


def compute_bone_delta(current_dir: Vec3, rest_dir: Vec3) -> Quat:
    """Rotation taking rest_dir to current_dir (pose delta)."""
    return quat_from_two_vectors(rest_dir, current_dir)


def rotate_landmarks(landmarks: Dict[str, Landmark], q: Quat) -> Dict[str, Landmark]:
    if q.w > 0.999999 and abs(q.x) + abs(q.y) + abs(q.z) < 1e-9:
        return landmarks
    return {
        name: Landmark(name, quat_rotate(q, lm.position), lm.confidence, lm.valid)
        for name, lm in landmarks.items()
    }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def _aspect_corrected(lm: Landmark, aspect: float) -> Vec3:
    return Vec3(lm.position.x * aspect, lm.position.y, 0.0)


def _image_positions(landmarks: Dict[str, Landmark], aspect: float) -> Dict[str, Landmark]:
    return {
        name: Landmark(name, _aspect_corrected(lm, aspect), lm.confidence, lm.valid)
        for name, lm in landmarks.items()
    }


def estimate_metres_per_unit(
    image_landmarks: Dict[str, Landmark],
    world_landmarks: Dict[str, Landmark],
    aspect: float = 1.0,
) -> float:
    """Apparent scale of the subject: metres per (aspect-corrected) image unit.

    Each body segment gives metric_length / image_length; foreshortened segments
    overestimate, so the smallest ratios are the most reliable. Returns 0 when
    nothing usable is visible.
    """
    img = _image_positions(image_landmarks, aspect)
    ratios: List[float] = []
    for a, b in _SIZE_SEGMENTS:
        pa, pb = resolve_landmark_position(a, img), resolve_landmark_position(b, img)
        wa, wb = resolve_landmark_position(a, world_landmarks), resolve_landmark_position(b, world_landmarks)
        if None in (pa, pb, wa, wb):
            continue
        image_len = (pb - pa).length()
        metric_len = (wb - wa).length()
        if image_len > 1e-4 and metric_len > 1e-4:
            ratios.append(metric_len / image_len)
    if not ratios:
        return 0.0
    ratios.sort()
    best = ratios[:2]
    return sum(best) / len(best)


def build_root_reference(
    image_landmarks: Dict[str, Landmark],
    world_landmarks: Dict[str, Landmark],
    aspect: float = 1.0,
    distance: float = 2.0,
) -> RootReference:
    hips = resolve_landmark_position("hips_mid", _image_positions(image_landmarks, aspect))
    mpu = estimate_metres_per_unit(image_landmarks, world_landmarks, aspect)
    if hips is None or mpu <= 0.0:
        return RootReference()
    return RootReference(hips_image=hips, metres_per_unit=mpu, distance=distance, valid=True)


def root_offset_metres(
    image_landmarks: Dict[str, Landmark],
    world_landmarks: Dict[str, Landmark],
    reference: RootReference,
    aspect: float = 1.0,
) -> Optional[Vec3]:
    """Hip displacement since the reference, metres in backend coords (x left, y up, z toward camera)."""
    if not reference.valid:
        return None
    hips = resolve_landmark_position("hips_mid", _image_positions(image_landmarks, aspect))
    mpu = estimate_metres_per_unit(image_landmarks, world_landmarks, aspect)
    if hips is None or mpu <= 0.0:
        return None
    depth_now = reference.distance * (mpu / reference.metres_per_unit)
    dx = hips.x * mpu - reference.hips_image.x * reference.metres_per_unit
    dy = hips.y * mpu - reference.hips_image.y * reference.metres_per_unit
    return Vec3(dx, dy, -(depth_now - reference.distance))


def world_correction_from_landmarks(landmarks: Dict[str, Landmark]) -> Quat:
    """Rotation that makes the measured body frame upright and camera-facing."""
    frame = body_frame_from_landmarks("hips", landmarks)
    if frame is None:
        return quat_identity()
    return quat_conjugate(frame_to_quat(frame))


def build_calibration_from_landmarks(
    landmarks: Dict[str, Landmark],
    roles: Optional[list] = None,
    image_landmarks: Optional[Dict[str, Landmark]] = None,
    aspect: float = 1.0,
    distance: float = 2.0,
) -> CalibrationData:
    """Build CalibrationData from one (averaged) frame of metric landmarks."""
    roles = roles or list(ROLE_LANDMARK_PAIRS.keys())
    cal = CalibrationData(valid=True)
    for name, lm in landmarks.items():
        if lm.valid:
            cal.average_landmarks[name] = lm.position

    cal.world_correction = world_correction_from_landmarks(landmarks)
    corrected = rotate_landmarks(landmarks, cal.world_correction)

    for role in roles:
        d = bone_direction_from_landmarks(role, corrected)
        if d is not None and d.length() > 1e-6:
            cal.bone_rest_dirs[role] = d
    for role in ROLE_FRAME_SPEC:
        frame = body_frame_from_landmarks(role, corrected)
        if frame is not None:
            cal.role_frames[role] = frame

    mid_h = resolve_landmark_position("hips_mid", corrected)
    mid_s = resolve_landmark_position("shoulders_mid", corrected)
    if mid_h and mid_s:
        cal.torso_length = (mid_s - mid_h).length()
        cal.scale = cal.torso_length or 1.0
    if image_landmarks:
        cal.root_reference = build_root_reference(image_landmarks, landmarks, aspect, distance)
    return cal


def average_landmark_frames(samples: list) -> Dict[str, Landmark]:
    """Average a list of landmark dicts (or Vec3 dicts); invalid entries are skipped."""
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
    return {
        name: Landmark(name, Vec3(s.x / counts[name], s.y / counts[name], s.z / counts[name]), 1.0, True)
        for name, s in sums.items()
    }


def average_calibrations(
    samples: list,
    image_samples: Optional[list] = None,
    aspect: float = 1.0,
    distance: float = 2.0,
) -> CalibrationData:
    """Average multiple landmark frames into one CalibrationData."""
    if not samples:
        return CalibrationData(valid=False)
    avg = average_landmark_frames(samples)
    avg_image = average_landmark_frames(image_samples) if image_samples else None
    return build_calibration_from_landmarks(avg, image_landmarks=avg_image, aspect=aspect, distance=distance)


# ---------------------------------------------------------------------------
# Pure targets (no bpy)
# ---------------------------------------------------------------------------

@dataclass
class PoseTargets:
    """World-space targets in Blender coordinates, keyed by bone name."""

    directions: Dict[str, Vec3] = field(default_factory=dict)
    frame_deltas: Dict[str, Quat] = field(default_factory=dict)
    root_offset_m: Optional[Vec3] = None  # Blender coords, metres


def compute_pose_targets(
    landmarks: Dict[str, Landmark],
    role_to_bone: Dict[str, str],
    calibration: Optional[CalibrationData] = None,
    image_landmarks: Optional[Dict[str, Landmark]] = None,
    aspect: float = 1.0,
    root_reference: Optional[RootReference] = None,
) -> PoseTargets:
    """Turn landmarks into per-bone world targets (directions / frame deltas / root)."""
    targets = PoseTargets()
    if not landmarks:
        return targets
    correction = calibration.world_correction if (calibration and calibration.valid) else quat_identity()
    corrected = rotate_landmarks(landmarks, correction)

    for role, bone_name in role_to_bone.items():
        if not bone_name:
            continue
        if role in ROLE_FRAME_SPEC:
            frame = body_frame_from_landmarks(role, corrected)
            if frame is not None:
                q_cur = frame_to_quat(frame)
                ref = calibration.role_frames.get(role) if (calibration and calibration.valid) else None
                q_ref = frame_to_quat(ref) if ref is not None else quat_identity()
                targets.frame_deltas[bone_name] = to_blender_quat(quat_mul(q_cur, quat_conjugate(q_ref)))
                continue
        d = bone_direction_from_landmarks(role, corrected)
        if d is not None:
            targets.directions[bone_name] = to_blender_vec(d)

    ref = root_reference or (calibration.root_reference if (calibration and calibration.valid) else None)
    if ref is not None and ref.valid and image_landmarks:
        offset = root_offset_metres(image_landmarks, landmarks, ref, aspect)
        if offset is not None:
            targets.root_offset_m = to_blender_vec(quat_rotate(correction, offset))
    return targets


def apply_landmarks_to_rotations(
    landmarks: Dict[str, Landmark],
    role_to_bone: Dict[str, str],
    calibration: Optional[CalibrationData] = None,
    armature_obj=None,
) -> Dict[str, Quat]:
    """Return bone_name → rotation for mapped roles.

    With an armature the rotations are bone-local (ready for ``rotation_quaternion``).
    Without one (offline tests) each is the world swing from the rig-agnostic rest
    direction (+Z up in Blender coordinates) to the tracked direction.
    """
    if armature_obj is not None:
        return solve_pose(landmarks, role_to_bone, calibration, armature_obj).rotations
    targets = compute_pose_targets(landmarks, role_to_bone, calibration)
    result: Dict[str, Quat] = {}
    for bone_name, q in targets.frame_deltas.items():
        result[bone_name] = quat_normalize(q)
    for bone_name, d in targets.directions.items():
        result[bone_name] = quat_normalize(compute_bone_delta(d, Vec3(0.0, 0.0, 1.0)))
    return result


# ---------------------------------------------------------------------------
# Armature solve (bpy / mathutils)
# ---------------------------------------------------------------------------

def rig_torso_length(armature_obj, role_to_bone: Dict[str, str]) -> float:
    """World-space hips → shoulders distance of the rig in rest pose (0 if unknown)."""
    bones = armature_obj.data.bones
    matrix = armature_obj.matrix_world
    hips = bones.get(role_to_bone.get("hips", ""))
    if hips is None:
        return 0.0
    hips_pos = matrix @ hips.head_local
    shoulder_points = []
    for role in ("upper_arm_L", "upper_arm_R"):
        b = bones.get(role_to_bone.get(role, ""))
        if b is not None:
            shoulder_points.append(matrix @ b.head_local)
    if len(shoulder_points) == 2:
        mid = (shoulder_points[0] + shoulder_points[1]) * 0.5
        return (mid - hips_pos).length
    for role in ("neck", "head", "chest", "spine"):
        b = bones.get(role_to_bone.get(role, ""))
        if b is not None:
            return (matrix @ b.head_local - hips_pos).length
    return 0.0


def solve_pose(
    landmarks: Dict[str, Landmark],
    role_to_bone: Dict[str, str],
    calibration: Optional[CalibrationData],
    armature_obj,
    image_landmarks: Optional[Dict[str, Landmark]] = None,
    aspect: float = 1.0,
    root_reference: Optional[RootReference] = None,
    root_motion: bool = False,
    root_scale: float = 1.0,
    rig_scale: Optional[float] = None,
) -> PoseSolution:
    """Solve bone-local rotations (and hips translation) for ``armature_obj``."""
    from mathutils import Matrix, Quaternion, Vector

    targets = compute_pose_targets(
        landmarks, role_to_bone, calibration, image_landmarks, aspect, root_reference
    )
    solution = PoseSolution()
    if not targets.directions and not targets.frame_deltas and targets.root_offset_m is None:
        return solution

    object_matrix = armature_obj.matrix_world.to_3x3()
    world_to_armature = object_matrix.inverted_safe()
    bones = armature_obj.data.bones
    rest_rotations = {b.name: b.matrix_local.to_quaternion() for b in bones}

    def to_vec(v: Vec3) -> "Vector":
        return Vector((v.x, v.y, v.z))

    def to_quat(q: Quat) -> "Quaternion":
        return Quaternion((q.w, q.x, q.y, q.z))

    # Direction targets → armature space
    dir_targets = {
        name: (world_to_armature @ to_vec(d)).normalized()
        for name, d in targets.directions.items()
        if name in rest_rotations
    }

    # Frame targets: rotate the bone's world rest axes by the body delta, back to armature space
    frame_targets = {}
    for name, dq in targets.frame_deltas.items():
        rest = rest_rotations.get(name)
        if rest is None:
            continue
        delta = to_quat(dq)
        axes = []
        for axis in (Vector((1, 0, 0)), Vector((0, 1, 0))):
            world_axis = object_matrix @ (rest @ axis)
            axes.append((world_to_armature @ (delta @ world_axis)).normalized())
        x_axis, y_axis = axes
        x_axis = (x_axis - y_axis * x_axis.dot(y_axis)).normalized()
        if x_axis.length < 1e-6:
            continue
        z_axis = x_axis.cross(y_axis).normalized()
        frame_targets[name] = Matrix((x_axis, y_axis, z_axis)).transposed().to_quaternion()

    root_bone = role_to_bone.get("hips", "")
    root_local_offset = None
    if root_motion and targets.root_offset_m is not None and root_bone in rest_rotations:
        scale = rig_scale
        if scale is None:
            torso_m = calibration.torso_length if (calibration and calibration.valid) else 0.0
            if torso_m <= 0.0:
                mid_h = resolve_landmark_position("hips_mid", landmarks)
                mid_s = resolve_landmark_position("shoulders_mid", landmarks)
                torso_m = (mid_s - mid_h).length() if (mid_h and mid_s) else 0.0
            rig_len = rig_torso_length(armature_obj, role_to_bone)
            scale = (rig_len / torso_m) if (torso_m > 1e-6 and rig_len > 1e-6) else 1.0
        offset_world = to_vec(targets.root_offset_m) * (scale * root_scale)
        solution.root_offset = Vec3(*offset_world)
        root_local_offset = world_to_armature @ offset_world

    solved: Dict[str, "Quaternion"] = {}
    pose_bones = armature_obj.pose.bones

    def solve(pb):
        if pb.name in solved:
            return solved[pb.name]
        parent_orientation = solve(pb.parent) if pb.parent else Quaternion()
        parent_rest = rest_rotations[pb.parent.name] if pb.parent else Quaternion()
        relative_rest = parent_rest.inverted() @ rest_rotations[pb.name]
        follow = (parent_orientation @ relative_rest).normalized()
        if pb.name in frame_targets:
            orientation = frame_targets[pb.name]
        elif pb.name in dir_targets:
            follow_dir = follow @ Vector((0.0, 1.0, 0.0))
            orientation = (follow_dir.rotation_difference(dir_targets[pb.name]) @ follow).normalized()
        else:
            orientation = (follow @ pb.matrix_basis.to_quaternion()).normalized()
            solved[pb.name] = orientation
            return orientation
        local = (follow.inverted() @ orientation).normalized()
        solution.rotations[pb.name] = Quat(local.w, local.x, local.y, local.z)
        if pb.name == root_bone and root_local_offset is not None:
            local_offset = follow.inverted() @ root_local_offset
            solution.locations[pb.name] = Vec3(*local_offset)
        solved[pb.name] = orientation
        return orientation

    for pb in pose_bones:
        solve(pb)
    return solution


def apply_rotations_to_armature(armature_obj, bone_rotations: Dict[str, Quat]) -> int:
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


def apply_solution_to_armature(armature_obj, solution: PoseSolution) -> int:
    """Write rotations and root locations onto pose bones. Returns count applied."""
    count = apply_rotations_to_armature(armature_obj, solution.rotations)
    try:
        from mathutils import Vector
    except ImportError:
        return count
    for bone_name, loc in solution.locations.items():
        pb = armature_obj.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.location = Vector((loc.x, loc.y, loc.z))
        count += 1
    return count

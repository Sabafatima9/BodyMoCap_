"""Pure 3D math helpers (no bpy)."""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .types import Quat, Vec3


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def vec_lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return Vec3(
        lerp(a.x, b.x, t),
        lerp(a.y, b.y, t),
        lerp(a.z, b.z, t),
    )


def quat_identity() -> Quat:
    return Quat(1.0, 0.0, 0.0, 0.0)


def quat_normalize(q: Quat) -> Quat:
    n = math.sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z)
    if n < 1e-12:
        return quat_identity()
    return Quat(q.w / n, q.x / n, q.y / n, q.z / n)


def quat_conjugate(q: Quat) -> Quat:
    return Quat(q.w, -q.x, -q.y, -q.z)


def quat_mul(a: Quat, b: Quat) -> Quat:
    return Quat(
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    )


def quat_slerp(a: Quat, b: Quat, t: float) -> Quat:
    a = quat_normalize(a)
    b = quat_normalize(b)
    dot = a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z
    if dot < 0.0:
        b = Quat(-b.w, -b.x, -b.y, -b.z)
        dot = -dot
    if dot > 0.9995:
        return quat_normalize(
            Quat(
                lerp(a.w, b.w, t),
                lerp(a.x, b.x, t),
                lerp(a.y, b.y, t),
                lerp(a.z, b.z, t),
            )
        )
    theta_0 = math.acos(clamp(dot, -1.0, 1.0))
    theta = theta_0 * t
    s0 = math.cos(theta) - dot * math.sin(theta) / math.sin(theta_0)
    s1 = math.sin(theta) / math.sin(theta_0)
    return Quat(
        s0 * a.w + s1 * b.w,
        s0 * a.x + s1 * b.x,
        s0 * a.y + s1 * b.y,
        s0 * a.z + s1 * b.z,
    )


def quat_from_two_vectors(from_v: Vec3, to_v: Vec3) -> Quat:
    """Smallest rotation taking from_v to to_v."""
    a = from_v.normalized()
    b = to_v.normalized()
    d = a.dot(b)
    if d > 0.999999:
        return quat_identity()
    if d < -0.999999:
        axis = Vec3(1, 0, 0).cross(a)
        if axis.length() < 1e-6:
            axis = Vec3(0, 1, 0).cross(a)
        axis = axis.normalized()
        return Quat(0.0, axis.x, axis.y, axis.z)
    c = a.cross(b)
    q = Quat(1.0 + d, c.x, c.y, c.z)
    return quat_normalize(q)


def quat_average(quats: Sequence[Quat]) -> Quat:
    """Markley-style average via summed quaternion (sign-aligned)."""
    if not quats:
        return quat_identity()
    if len(quats) == 1:
        return quat_normalize(quats[0])
    acc = Quat(0, 0, 0, 0)
    ref = quat_normalize(quats[0])
    for q in quats:
        q = quat_normalize(q)
        if (q.w * ref.w + q.x * ref.x + q.y * ref.y + q.z * ref.z) < 0:
            q = Quat(-q.w, -q.x, -q.y, -q.z)
        acc = Quat(acc.w + q.w, acc.x + q.x, acc.y + q.y, acc.z + q.z)
    return quat_normalize(acc)


def quat_swing_from_parent(parent_dir: Vec3, child_dir: Vec3) -> Quat:
    """Swing rotation from parent bone direction to child bone direction."""
    return quat_from_two_vectors(parent_dir, child_dir)


def cumulative_quat_product(quats: Sequence[Quat]) -> Quat:
    r = quat_identity()
    for q in quats:
        r = quat_mul(r, q)
    return r


def chain_rest_lengths(positions: Sequence[Vec3]) -> List[float]:
    """Segment lengths between consecutive joint positions."""
    lengths: List[float] = []
    for i in range(len(positions) - 1):
        lengths.append((positions[i + 1] - positions[i]).length())
    return lengths


def normalize_weights(lengths: Sequence[float]) -> List[float]:
    total = sum(lengths)
    if total < 1e-12:
        n = len(lengths)
        return [1.0 / n] * n if n else []
    return [L / total for L in lengths]


def direction_from_landmarks(parent: Vec3, child: Vec3) -> Vec3:
    return (child - parent).normalized()


def euler_xyz_to_quat(rx: float, ry: float, rz: float) -> Quat:
    """Euler XYZ radians → quaternion."""
    cx, sx = math.cos(rx * 0.5), math.sin(rx * 0.5)
    cy, sy = math.cos(ry * 0.5), math.sin(ry * 0.5)
    cz, sz = math.cos(rz * 0.5), math.sin(rz * 0.5)
    return quat_normalize(
        Quat(
            cx * cy * cz + sx * sy * sz,
            sx * cy * cz - cx * sy * sz,
            cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz,
        )
    )


def quat_angle_deg(a: Quat, b: Quat) -> float:
    """Angular difference in degrees between two unit quaternions."""
    a = quat_normalize(a)
    b = quat_normalize(b)
    d = abs(a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z)
    d = clamp(d, 0.0, 1.0)
    return math.degrees(2.0 * math.acos(d))


def quat_rotate(q: Quat, v: Vec3) -> Vec3:
    """Rotate vector v by unit quaternion q."""
    qv = Quat(0.0, v.x, v.y, v.z)
    r = quat_mul(quat_mul(q, qv), quat_conjugate(q))
    return Vec3(r.x, r.y, r.z)


def quat_from_matrix(m: Sequence[Sequence[float]]) -> Quat:
    """Rotation matrix (rows) → quaternion (Shepperd's method)."""
    m00, m01, m02 = m[0]
    m10, m11, m12 = m[1]
    m20, m21, m22 = m[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        return quat_normalize(Quat(0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s))
    if m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        return quat_normalize(Quat((m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s))
    if m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        return quat_normalize(Quat((m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s))
    s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
    return quat_normalize(Quat((m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s))


def quat_from_frame(x_axis: Vec3, y_axis: Vec3, z_axis: Vec3) -> Quat:
    """Quaternion whose rotation maps the identity basis onto the given (orthonormal) axes."""
    return quat_from_matrix(
        (
            (x_axis.x, y_axis.x, z_axis.x),
            (x_axis.y, y_axis.y, z_axis.y),
            (x_axis.z, y_axis.z, z_axis.z),
        )
    )


def orthonormal_frame(lateral: Vec3, up: Vec3) -> Tuple[Vec3, Vec3, Vec3]:
    """Right-handed frame (lateral, up, forward) from a lateral and an up hint.

    ``up`` is kept exact; ``lateral`` is made orthogonal to it. Returns
    ``forward = lateral × up`` so that (lateral, up, forward) matches the identity
    basis for a subject facing the camera: x = subject's left, y = up, z = toward camera.
    """
    y = up.normalized()
    x = lateral - y * lateral.dot(y)
    if x.length() < 1e-6:
        # Degenerate hint (lateral ∥ up): pick any perpendicular direction
        helper = Vec3(1.0, 0.0, 0.0) if abs(y.x) < 0.9 else Vec3(0.0, 0.0, 1.0)
        x = helper - y * helper.dot(y)
    x = x.normalized()
    z = x.cross(y).normalized()
    return x, y, z


def frame_quat(lateral: Vec3, up: Vec3) -> Quat:
    """Rotation from the identity body frame to the frame spanned by (lateral, up)."""
    x, y, z = orthonormal_frame(lateral, up)
    return quat_from_frame(x, y, z)

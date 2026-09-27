"""Shared types for BodyMocap (pure Python, no bpy)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple


class TrackingState(Enum):
    """Pose tracking quality (FR-023)."""

    OK = auto()
    DEGRADED = auto()
    LOST = auto()


class RestPoseStyle(Enum):
    T_POSE = "T_POSE"
    A_POSE = "A_POSE"


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    def __rmul__(self, s: float) -> "Vec3":
        return self.__mul__(s)

    def length(self) -> float:
        return (self.x * self.x + self.y * self.y + self.z * self.z) ** 0.5

    def normalized(self) -> "Vec3":
        L = self.length()
        if L < 1e-12:
            return Vec3(0.0, 0.0, 0.0)
        return Vec3(self.x / L, self.y / L, self.z / L)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )


@dataclass
class Quat:
    """Quaternion w, x, y, z (scalar-first)."""

    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> Tuple[float, float, float, float]:
        return (self.w, self.x, self.y, self.z)

    def as_xyzw(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.z, self.w)


@dataclass
class Landmark:
    name: str
    position: Vec3
    confidence: float = 1.0
    valid: bool = True


@dataclass
class PoseFrame:
    """One frame of pose estimation output.

    ``landmarks`` are image-normalized (x centred on 0, y up, z depth-ish) and
    drive the 2D overlay and root translation. ``world_landmarks`` are metric
    3D positions (metres, hip-centred, y up, z toward the camera) and drive bone
    directions; when a backend cannot provide them they are left empty and the
    solver falls back to ``landmarks``.
    """

    landmarks: Dict[str, Landmark] = field(default_factory=dict)
    tracking_state: TrackingState = TrackingState.LOST
    timestamp: float = 0.0
    frame_index: int = 0
    world_landmarks: Dict[str, Landmark] = field(default_factory=dict)
    aspect: float = 1.0  # frame width / height, for aspect-correct image coords

    def solve_landmarks(self) -> Dict[str, Landmark]:
        """Landmarks to use for 3D bone directions."""
        return self.world_landmarks or self.landmarks


@dataclass
class BoneRotationSample:
    """Per-bone rotation at a recording frame (quaternion wxyz)."""

    bone_name: str
    rotation: Quat


@dataclass
class RecordingFrame:
    frame_index: int
    bone_rotations: Dict[str, Quat] = field(default_factory=dict)
    tracking_state: TrackingState = TrackingState.OK
    timestamp: float = 0.0
    bone_locations: Dict[str, Vec3] = field(default_factory=dict)


@dataclass
class PoseSolution:
    """Solved pose for one frame: bone-local rotations plus root translation."""

    rotations: Dict[str, Quat] = field(default_factory=dict)
    locations: Dict[str, Vec3] = field(default_factory=dict)
    root_offset: Vec3 = field(default_factory=Vec3)  # world-space, rig units

    def __bool__(self) -> bool:
        return bool(self.rotations or self.locations)


@dataclass
class MappingEntry:
    role: str
    bone_name: str
    landmark_parent: str = ""
    landmark_child: str = ""


@dataclass
class MappingQuality:
    unmapped_roles: List[str] = field(default_factory=list)
    duplicate_bones: List[str] = field(default_factory=list)
    bones_without_source: List[str] = field(default_factory=list)
    mapped_count: int = 0

    @property
    def ok(self) -> bool:
        return (
            len(self.unmapped_roles) == 0
            and len(self.duplicate_bones) == 0
        )


@dataclass
class ChainDefinition:
    name: str
    bone_names: List[str]
    side: str = ""  # L, R, or ""


@dataclass
class Frame3:
    """Right-handed orthonormal body frame: lateral (subject's left), up, forward."""

    lateral: Vec3 = field(default_factory=lambda: Vec3(1.0, 0.0, 0.0))
    up: Vec3 = field(default_factory=lambda: Vec3(0.0, 1.0, 0.0))
    forward: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 1.0))


@dataclass
class RootReference:
    """Image-space reference for root translation (aspect-corrected units)."""

    hips_image: Vec3 = field(default_factory=Vec3)
    metres_per_unit: float = 0.0  # metric size / image size at reference depth
    distance: float = 2.0  # assumed camera distance at the reference (metres)
    valid: bool = False


@dataclass
class CalibrationData:
    rest_style: RestPoseStyle = RestPoseStyle.T_POSE
    average_landmarks: Dict[str, Vec3] = field(default_factory=dict)
    scale: float = 1.0
    facing: Vec3 = field(default_factory=lambda: Vec3(0.0, -1.0, 0.0))
    bone_rest_dirs: Dict[str, Vec3] = field(default_factory=dict)
    valid: bool = False
    # Rotation (backend coords) that makes the calibrated body upright and
    # facing the camera: removes camera tilt/roll and the subject's yaw.
    world_correction: Quat = field(default_factory=Quat)
    # Per-role body frames measured after correction (torso/head roles).
    role_frames: Dict[str, Frame3] = field(default_factory=dict)
    torso_length: float = 0.0  # metres, hips_mid -> shoulders_mid
    root_reference: RootReference = field(default_factory=RootReference)

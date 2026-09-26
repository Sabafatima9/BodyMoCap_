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
    """One frame of pose estimation output."""

    landmarks: Dict[str, Landmark] = field(default_factory=dict)
    tracking_state: TrackingState = TrackingState.LOST
    timestamp: float = 0.0
    frame_index: int = 0


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
class CalibrationData:
    rest_style: RestPoseStyle = RestPoseStyle.T_POSE
    average_landmarks: Dict[str, Vec3] = field(default_factory=dict)
    scale: float = 1.0
    facing: Vec3 = field(default_factory=lambda: Vec3(0.0, -1.0, 0.0))
    bone_rest_dirs: Dict[str, Vec3] = field(default_factory=dict)
    valid: bool = False

"""MediaPipe Pose 33-landmark naming and semantic roles (pure Python)."""

from __future__ import annotations

from typing import Dict, List, Tuple

# Standard MediaPipe Pose landmark index → name
MEDIAPIPE_POSE_NAMES: Dict[int, str] = {
    0: "nose",
    1: "left_eye_inner",
    2: "left_eye",
    3: "left_eye_outer",
    4: "right_eye_inner",
    5: "right_eye",
    6: "right_eye_outer",
    7: "left_ear",
    8: "right_ear",
    9: "mouth_left",
    10: "mouth_right",
    11: "left_shoulder",
    12: "right_shoulder",
    13: "left_elbow",
    14: "right_elbow",
    15: "left_wrist",
    16: "right_wrist",
    17: "left_pinky",
    18: "right_pinky",
    19: "left_index",
    20: "right_index",
    21: "left_thumb",
    22: "right_thumb",
    23: "left_hip",
    24: "right_hip",
    25: "left_knee",
    26: "right_knee",
    27: "left_ankle",
    28: "right_ankle",
    29: "left_heel",
    30: "right_heel",
    31: "left_foot_index",
    32: "right_foot_index",
}

# Skeleton edges for overlay (parent, child)
POSE_CONNECTIONS: List[Tuple[str, str]] = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
    ("left_ankle", "left_foot_index"),
    ("right_ankle", "right_foot_index"),
    ("nose", "left_shoulder"),
    ("nose", "right_shoulder"),
]

# Semantic bone roles → (parent_landmark, child_landmark)
ROLE_LANDMARK_PAIRS: Dict[str, Tuple[str, str]] = {
    "hips": ("left_hip", "right_hip"),  # special: mid-hip orientation
    "spine": ("hips_mid", "shoulders_mid"),
    "chest": ("hips_mid", "shoulders_mid"),
    "neck": ("shoulders_mid", "nose"),
    "head": ("shoulders_mid", "nose"),
    "upper_arm_L": ("left_shoulder", "left_elbow"),
    "forearm_L": ("left_elbow", "left_wrist"),
    "hand_L": ("left_wrist", "left_index"),
    "upper_arm_R": ("right_shoulder", "right_elbow"),
    "forearm_R": ("right_elbow", "right_wrist"),
    "hand_R": ("right_wrist", "right_index"),
    "thigh_L": ("left_hip", "left_knee"),
    "shin_L": ("left_knee", "left_ankle"),
    "foot_L": ("left_ankle", "left_foot_index"),
    "thigh_R": ("right_hip", "right_knee"),
    "shin_R": ("right_knee", "right_ankle"),
    "foot_R": ("right_ankle", "right_foot_index"),
    "clavicle_L": ("shoulders_mid", "left_shoulder"),
    "clavicle_R": ("shoulders_mid", "right_shoulder"),
}

REQUIRED_ROLES: List[str] = [
    "hips",
    "spine",
    "upper_arm_L",
    "forearm_L",
    "upper_arm_R",
    "forearm_R",
    "thigh_L",
    "shin_L",
    "thigh_R",
    "shin_R",
]


def mid_name(a: str, b: str) -> str:
    return f"mid_{a}_{b}"

"""Humanoid hierarchy templates and bone-name heuristics (FR-040, FR-043)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from ..core.landmarks import REQUIRED_ROLES, ROLE_LANDMARK_PAIRS

# Semantic roles in hierarchical order
HUMANOID_ROLES: List[str] = [
    "hips",
    "spine",
    "chest",
    "neck",
    "head",
    "clavicle_L",
    "upper_arm_L",
    "forearm_L",
    "hand_L",
    "clavicle_R",
    "upper_arm_R",
    "forearm_R",
    "hand_R",
    "thigh_L",
    "shin_L",
    "foot_L",
    "thigh_R",
    "shin_R",
    "foot_R",
]

# Role → list of regex patterns (normalized bone name)
ROLE_NAME_HEURISTICS: Dict[str, List[str]] = {
    "hips": [r"^hips?$", r"^pelvis$", r"^root$", r"^hip$", r"^cog$"],
    "spine": [r"^spine$", r"^spine[_]?0?1$", r"^spine1$", r"^torso$"],
    "chest": [r"^spine[_]?0?2$", r"^spine2$", r"^chest$", r"^ribcage$", r"^spine[_]?0?3$"],
    "neck": [r"^neck$", r"^neck[_]?0?1$"],
    "head": [r"^head$", r"^skull$"],
    "clavicle_L": [r"^clavicle[._]?l$", r"^shoulder[._]?l$", r"^l[._]?clavicle$"],
    "upper_arm_L": [
        r"^upperarm[._]?l$", r"^arm[._]?l$", r"^l[._]?upperarm$", r"^leftarm$",
        r"^upper_arm[._]?l$", r"^l[._]?arm$",
    ],
    "forearm_L": [
        r"^forearm[._]?l$", r"^lowerarm[._]?l$", r"^l[._]?forearm$",
        r"^leftforearm$", r"^elbow[._]?l$",
    ],
    "hand_L": [r"^hand[._]?l$", r"^wrist[._]?l$", r"^l[._]?hand$", r"^lefthand$"],
    "clavicle_R": [r"^clavicle[._]?r$", r"^shoulder[._]?r$", r"^r[._]?clavicle$"],
    "upper_arm_R": [
        r"^upperarm[._]?r$", r"^arm[._]?r$", r"^r[._]?upperarm$", r"^rightarm$",
        r"^upper_arm[._]?r$", r"^r[._]?arm$",
    ],
    "forearm_R": [
        r"^forearm[._]?r$", r"^lowerarm[._]?r$", r"^r[._]?forearm$",
        r"^rightforearm$", r"^elbow[._]?r$",
    ],
    "hand_R": [r"^hand[._]?r$", r"^wrist[._]?r$", r"^r[._]?hand$", r"^righthand$"],
    "thigh_L": [
        r"^thigh[._]?l$", r"^upleg[._]?l$", r"^upperleg[._]?l$", r"^l[._]?thigh$",
        r"^leftupleg$", r"^leg[._]?l$",
    ],
    "shin_L": [
        r"^shin[._]?l$", r"^calf[._]?l$", r"^lowerleg[._]?l$", r"^l[._]?shin$",
        r"^leftleg$", r"^knee[._]?l$",
    ],
    "foot_L": [r"^foot[._]?l$", r"^ankle[._]?l$", r"^l[._]?foot$", r"^leftfoot$"],
    "thigh_R": [
        r"^thigh[._]?r$", r"^upleg[._]?r$", r"^upperleg[._]?r$", r"^r[._]?thigh$",
        r"^rightupleg$", r"^leg[._]?r$",
    ],
    "shin_R": [
        r"^shin[._]?r$", r"^calf[._]?r$", r"^lowerleg[._]?r$", r"^r[._]?shin$",
        r"^rightleg$", r"^knee[._]?r$",
    ],
    "foot_R": [r"^foot[._]?r$", r"^ankle[._]?r$", r"^r[._]?foot$", r"^rightfoot$"],
}


def normalize_bone_name(name: str) -> str:
    n = name.strip().lower()
    n = n.replace("-", "").replace(" ", "")
    # Mixamo style: mixamorig:LeftArm → leftarm handled via word patterns below
    if ":" in n:
        n = n.split(":")[-1]
    # Convert LeftArm / RightArm to side suffix form for matching
    n = re.sub(r"^left", "l_", n)
    n = re.sub(r"^right", "r_", n)
    return n


def match_role(bone_name: str, role: str) -> bool:
    patterns = ROLE_NAME_HEURISTICS.get(role, [])
    n = normalize_bone_name(bone_name)
    # Also try original-ish forms
    variants = {n, bone_name.lower().replace(" ", "").replace("-", "")}
    # Mixamo LeftArm
    raw = bone_name.lower()
    if "left" in raw:
        variants.add(re.sub(r"left", "l_", raw.replace(" ", "").replace("-", "")))
    if "right" in raw:
        variants.add(re.sub(r"right", "r_", raw.replace(" ", "").replace("-", "")))
    for v in variants:
        for pat in patterns:
            if re.search(pat, v):
                return True
    return False


def auto_map_bones(bone_names: Sequence[str]) -> Dict[str, str]:
    """Map semantic roles → bone names using heuristics. First match wins."""
    mapping: Dict[str, str] = {}
    used_bones = set()
    for role in HUMANOID_ROLES:
        for bn in bone_names:
            if bn in used_bones:
                continue
            if match_role(bn, role):
                mapping[role] = bn
                used_bones.add(bn)
                break
    return mapping


def role_landmark_pair(role: str) -> Optional[Tuple[str, str]]:
    return ROLE_LANDMARK_PAIRS.get(role)


def required_roles() -> List[str]:
    return list(REQUIRED_ROLES)

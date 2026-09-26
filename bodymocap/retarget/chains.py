"""Humanoid chain detection and definition (FR-071)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from ..core.types import ChainDefinition

# Heuristic name patterns per chain role
CHAIN_PATTERNS: Dict[str, List[str]] = {
    "spine": [
        r"hips?", r"pelvis", r"root", r"spine\d*", r"chest", r"torso", r"neck", r"head",
    ],
    "arm_L": [
        r"clavicle[._]?l", r"shoulder[._]?l", r"upperarm[._]?l", r"arm[._]?l",
        r"forearm[._]?l", r"lowerarm[._]?l", r"elbow[._]?l", r"hand[._]?l", r"wrist[._]?l",
    ],
    "arm_R": [
        r"clavicle[._]?r", r"shoulder[._]?r", r"upperarm[._]?r", r"arm[._]?r",
        r"forearm[._]?r", r"lowerarm[._]?r", r"elbow[._]?r", r"hand[._]?r", r"wrist[._]?r",
    ],
    "leg_L": [
        r"upleg[._]?l", r"thigh[._]?l", r"leg[._]?l", r"shin[._]?l",
        r"calf[._]?l", r"lowerleg[._]?l", r"foot[._]?l", r"ankle[._]?l", r"toe[._]?l",
    ],
    "leg_R": [
        r"upleg[._]?r", r"thigh[._]?r", r"leg[._]?r", r"shin[._]?r",
        r"calf[._]?r", r"lowerleg[._]?r", r"foot[._]?r", r"ankle[._]?r", r"toe[._]?r",
    ],
}


def _norm(name: str) -> str:
    return re.sub(r"[\s\-]+", "", name.lower())


def match_bone_to_patterns(bone_name: str, patterns: Sequence[str]) -> bool:
    n = _norm(bone_name)
    # Also try common .L / .R / _L / _R forms already in patterns
    for pat in patterns:
        if re.search(pat, n):
            return True
    # Blender style Left/Right words
    return False


def detect_chains(bone_names: Sequence[str]) -> Dict[str, ChainDefinition]:
    """Detect humanoid chains from a flat list of bone names."""
    chains: Dict[str, ChainDefinition] = {}
    used = set()
    for chain_name, patterns in CHAIN_PATTERNS.items():
        matched: List[str] = []
        for bn in bone_names:
            if bn in used:
                continue
            if match_bone_to_patterns(bn, patterns):
                matched.append(bn)
                used.add(bn)
        if matched:
            side = ""
            if chain_name.endswith("_L"):
                side = "L"
            elif chain_name.endswith("_R"):
                side = "R"
            chains[chain_name] = ChainDefinition(
                name=chain_name, bone_names=matched, side=side
            )
    return chains


def pair_chains(
    source: Dict[str, ChainDefinition],
    target: Dict[str, ChainDefinition],
) -> List[tuple]:
    """Return list of (src_chain, tgt_chain) for matching names."""
    pairs = []
    for name, src in source.items():
        if name in target:
            pairs.append((src, target[name]))
    return pairs


def manual_chain(name: str, bone_names: List[str], side: str = "") -> ChainDefinition:
    return ChainDefinition(name=name, bone_names=list(bone_names), side=side)

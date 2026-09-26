"""Auto-map operator helpers and quality report (FR-040, FR-045)."""

from __future__ import annotations

from typing import Dict, List, Sequence

from ..core.types import MappingQuality
from .templates import HUMANOID_ROLES, auto_map_bones, required_roles


def build_auto_mapping(bone_names: Sequence[str]) -> Dict[str, str]:
    return auto_map_bones(bone_names)


def evaluate_mapping_quality(
    role_to_bone: Dict[str, str],
    armature_bone_names: Sequence[str],
    required: Sequence[str] | None = None,
) -> MappingQuality:
    required = list(required) if required is not None else required_roles()
    bone_set = set(armature_bone_names)
    unmapped = [r for r in required if r not in role_to_bone or not role_to_bone[r]]

    bone_counts: Dict[str, int] = {}
    for role, bone in role_to_bone.items():
        if not bone:
            continue
        bone_counts[bone] = bone_counts.get(bone, 0) + 1
    duplicates = [b for b, c in bone_counts.items() if c > 1]

    mapped_bones = set(role_to_bone.values())
    without_source = [b for b in armature_bone_names if b not in mapped_bones]

    # Only flag missing bones that were mapped to non-existent names
    invalid = [b for b in role_to_bone.values() if b and b not in bone_set]
    if invalid:
        duplicates = list(set(duplicates) | set(invalid))

    return MappingQuality(
        unmapped_roles=unmapped,
        duplicate_bones=duplicates,
        bones_without_source=without_source,
        mapped_count=len([b for b in role_to_bone.values() if b]),
    )


def mapping_quality_message(q: MappingQuality) -> str:
    parts = [f"Mapped: {q.mapped_count}"]
    if q.unmapped_roles:
        parts.append(f"Unmapped roles: {', '.join(q.unmapped_roles)}")
    if q.duplicate_bones:
        parts.append(f"Duplicates/invalid: {', '.join(q.duplicate_bones)}")
    return " | ".join(parts)

"""JSON mapping preset save/load (FR-042). Pure Python."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


PRESET_VERSION = 1


def mapping_to_dict(
    role_to_bone: Dict[str, str],
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    entries = [
        {"role": role, "bone_name": bone}
        for role, bone in sorted(role_to_bone.items())
    ]
    return {
        "version": PRESET_VERSION,
        "type": "bodymocap_mapping_preset",
        "meta": meta or {},
        "entries": entries,
    }


def mapping_from_dict(data: Dict[str, Any]) -> Dict[str, str]:
    if data.get("type") and data["type"] != "bodymocap_mapping_preset":
        raise ValueError(f"Unknown preset type: {data.get('type')}")
    entries = data.get("entries", [])
    result: Dict[str, str] = {}
    for e in entries:
        role = e.get("role") or e.get("joint")
        bone = e.get("bone_name") or e.get("bone")
        if role and bone:
            result[str(role)] = str(bone)
    # Also accept flat dict form
    if not result and "mapping" in data and isinstance(data["mapping"], dict):
        result = {str(k): str(v) for k, v in data["mapping"].items()}
    return result


def save_preset(
    path: str,
    role_to_bone: Dict[str, str],
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = mapping_to_dict(role_to_bone, meta)
    text = json.dumps(data, indent=2)
    p.write_text(text, encoding="utf-8")
    return str(p)


def load_preset(path: str) -> Dict[str, str]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return mapping_from_dict(data)


def preset_to_json_string(role_to_bone: Dict[str, str], meta: Optional[Dict[str, Any]] = None) -> str:
    return json.dumps(mapping_to_dict(role_to_bone, meta), indent=2)


def preset_from_json_string(text: str) -> Dict[str, str]:
    return mapping_from_dict(json.loads(text))

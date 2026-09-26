"""Preset JSON roundtrip tests (FR-042)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bodymocap.mapping.presets import (
    load_preset,
    mapping_from_dict,
    mapping_to_dict,
    preset_from_json_string,
    preset_to_json_string,
    save_preset,
)


class TestPresets(unittest.TestCase):
    def test_roundtrip_dict(self):
        mapping = {
            "hips": "Hips",
            "spine": "Spine",
            "upper_arm_L": "LeftArm",
            "forearm_L": "LeftForeArm",
        }
        data = mapping_to_dict(mapping, meta={"armature": "Armature"})
        restored = mapping_from_dict(data)
        self.assertEqual(restored, mapping)

    def test_roundtrip_string(self):
        mapping = {"thigh_L": "Thigh.L", "shin_L": "Shin.L"}
        text = preset_to_json_string(mapping)
        restored = preset_from_json_string(text)
        self.assertEqual(restored, mapping)

    def test_roundtrip_file(self):
        mapping = {
            "upper_arm_R": "upperarm_r",
            "forearm_R": "forearm_r",
            "hand_R": "hand_r",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "preset.json"
            save_preset(str(path), mapping, meta={"v": 1})
            loaded = load_preset(str(path))
            self.assertEqual(loaded, mapping)
            raw = json.loads(path.read_text())
            self.assertEqual(raw["type"], "bodymocap_mapping_preset")
            self.assertEqual(raw["version"], 1)


if __name__ == "__main__":
    unittest.main()

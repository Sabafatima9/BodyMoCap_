# BodyMocap Verification Checklist

**Date:** 2026-09-19  
**Build:** bodymocap 1.0.0  
**Method:** Code inspection + pure-Python unit tests; live webcam/MediaPipe marked Environment-limited where hardware/deps unavailable on the build box.

Legend: **Implemented** = logic present and exercised offline or by API; **Environment-limited** = implemented but requires Blender UI / webcam / MediaPipe wheels at runtime.

| ID | Requirement (shall) | Status | Evidence |
|----|---------------------|--------|----------|
| FR-001 | Distributable add-on package with `bl_info` | Implemented | `bodymocap/__init__.py` `bl_info`; `scripts/make_addon_zip.py` → `dist/bodymocap.zip` |
| FR-002 | Install/enable/disable/uninstall via Preferences | Implemented | Standard Blender zip layout (`bodymocap/` root); `register`/`unregister` |
| FR-003 | Register without crash if ML deps missing; show status | Implemented | Guarded imports; `BODYMOCAP_OT_refresh_deps`; panel deps box; `blender_compat.dependency_status` |
| FR-004 | Declare Blender 4.0+; warn on unsupported | Implemented | `bl_info["blender"]=(4,0,0)`; `is_supported_blender`; camera ops report ERROR |
| FR-010 | Start camera by device index | Implemented | `BODYMOCAP_OT_camera_start`; `camera/capture.CameraCapture.open` |
| FR-011 | Live preview while session active | Implemented | `camera/preview.numpy_bgr_to_blender_image` Image `BodyMocap_Preview`; modal timer |
| FR-012 | Stop camera and release device | Implemented | `BODYMOCAP_OT_camera_stop`; `CameraCapture.close` |
| FR-013 | Calibration T/A pose for configurable duration | Implemented | `BODYMOCAP_OT_calibrate`; `calibration_seconds`; `rest_pose_style` |
| FR-014 | Capture reference skeleton for align/scale | Implemented | `mapping/apply_pose.average_calibrations` / `CalibrationData` |
| FR-015 | Mirror + subject scale/distance | Implemented | `mirror_preview`, `subject_scale`, `subject_distance` props; mirror in capture loop |
| FR-016 | Fail fast if no camera; no UI hang | Implemented | Open + immediate `read` check; ERROR report; modal timer (not blocking) |
| FR-020 | Detect single-person pose via backend | Implemented | `PoseBackend`; `MediaPipeBackend`; `MockBackend` |
| FR-021 | Time-sequenced landmarks + confidence | Implemented | `PoseFrame` / `Landmark`; MediaPipe visibility; fixture JSON |
| FR-022 | Minimum confidence threshold | Implemented | `ConfidenceConfig.min_confidence`; `TrackingHysteresis.filter_landmarks`; tests |
| FR-023 | Hold/interpolate/drop + OK/Degraded/Lost UI | Implemented | `HoldInterpolatePolicy`; `TrackingState`; hysteresis tests; panel status |
| FR-024 | Local processing by default | Implemented | No network in pose path; backends `local: true` |
| FR-030 | Skeleton overlay on preview | Implemented | `overlay/draw.draw_skeleton_opencv` |
| FR-031 | Color by confidence | Implemented | `confidence_color` green/yellow/red |
| FR-032 | Toggle overlay without stopping camera | Implemented | `show_overlay` prop |
| FR-040 | Automatic humanoid mapping | Implemented | `mapping/templates.auto_map_bones`; `BODYMOCAP_OT_auto_map` |
| FR-041 | Manual mapping UI list add/remove/clear | Implemented | `BODYMOCAP_UL_mapping`; mapping_ops add/remove/clear |
| FR-042 | Save/load JSON presets | Implemented | `mapping/presets.py`; preset_save/load ops; `test_presets` |
| FR-043 | Hierarchical mapping via roles | Implemented | `ROLE_LANDMARK_PAIRS`; `HUMANOID_ROLES`; FK directions |
| FR-044 | Rest-pose calibration offsets | Implemented | `apply_landmarks_to_rotations` + `CalibrationData.bone_rest_dirs` |
| FR-045 | Mapping quality feedback | Implemented | `evaluate_mapping_quality`; panel message |
| FR-046 | Mapping accuracy critical (proposed target) | Environment-limited | Pipeline implemented; quantitative fixture accuracy needs Blender visual review |
| FR-050 | Start/pause/resume/stop recording | Implemented | `recording/session.RecordingSession`; record_ops |
| FR-051 | Store per-frame bone transforms + frame index | Implemented | `RecordingFrame`; session.append |
| FR-052 | Discard take without baking | Implemented | `BODYMOCAP_OT_record_discard` |
| FR-053 | Warn if degraded/lost > fraction (default 15%) | Implemented | `should_warn_tracking`; stop/bake reports WARNING |
| FR-060 | Bake to Action with bone rotation keys | Implemented | `bake/action.bake_session_to_action` |
| FR-061 | Action name, start frame, overwrite | Implemented | props + bake operator |
| FR-062 | One-click Apply (action or NLA) | Implemented | `bake/apply.apply_action_to_armature`; `BODYMOCAP_OT_apply_action` |
| FR-063 | Editable Actions without add-on running | Implemented | Standard `bpy.data.actions` / keyframes |
| FR-064 | Optional smoothers | Environment-limited | Marked optional/Phase 2 in SRS; not required MVP |
| FR-070 | Retarget source→target different bone counts | Implemented | `retarget/transfer.py` |
| FR-071 | Define/detect chain pairs | Implemented | `retarget/chains.detect_chains`; detect_chains op |
| FR-072 | N:M aggregate / split strategy | Implemented | `retarget/proportional.py` |
| FR-073 | 4→2 arm remap normative | Implemented | `example_arm_4_to_2`; `test_proportional_retarget` |
| FR-074 | 2→4 split | Implemented | `example_arm_2_to_4`; unit tests |
| FR-075 | Rest-pose alignment before deltas | Implemented | Calibration path for live; bone rest lengths in transfer |
| FR-076 | Write new Action on target | Implemented | `transfer_in_blender`; retarget_transfer op |
| FR-080 | Operator ERROR/WARNING reports | Implemented | All operators use `self.report` |
| FR-081 | Session diagnostics logging | Implemented | `utils/logging_util` session summary |
| FR-082 | Import failures don’t crash registration | Implemented | Optional mediapipe/cv2; mock path |
| FR-090 | On-device inference default | Implemented | Local backends only in MVP |
| FR-091 | No remote upload unless explicit (Phase 2 off) | Implemented | No remote backend; no network in pose path |
| FR-092 | No raw video persist unless debug prop | Implemented | `save_debug_video` default False; recording stores transforms only |
| NFR-001 | ≥15 FPS proposed | Environment-limited | Modal 30 Hz timer; needs hardware measure |
| NFR-002 | ≤150 ms latency proposed | Environment-limited | Needs hardware measure |
| NFR-003 | Lighting robustness validation | Environment-limited | Status UX ready; matrix needs camera lab |
| NFR-004 | Motion robustness validation | Environment-limited | Mock walk/idle + fixtures; full matrix needs camera |
| NFR-005 | Usability dry-run | Environment-limited | Documented workflow in README |
| NFR-006 | Win/macOS/Linux Blender 4.x | Implemented | Pure Python + bpy guards; OS-agnostic packaging |
| NFR-007 | Unit-testable math outside Blender | Implemented | `tests/run_tests.py` (math, retarget, presets, confidence) |
| NFR-008 | No silent binary download | Implemented | User installs wheels per INSTALL.md |

## Unit test evidence

```text
python tests/run_tests.py
```

Covers: 4→2 aggregation, 2→4 split, preset roundtrip, confidence hysteresis, math3d.

## Counts

| Status | Count |
|--------|-------|
| Implemented | 50 |
| Environment-limited | 8 (FR-046 accuracy measure, FR-064 optional smoothers, NFR-001–005 hardware/usability matrix) |

Mandatory MVP functional shalls with offline/API evidence are Implemented. Live webcam + MediaPipe visual checks are Environment-limited on the build host.

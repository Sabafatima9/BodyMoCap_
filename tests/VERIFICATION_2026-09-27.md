# BodyMocap verification — 27 September 2026

Tested in Blender 5.2.1 LTS through the existing Blender MCP connection on port
9876. Updated package: **1.1.1**, installed and enabled in Blender's user add-ons
directory. The original scene remains in the saved file; test rigs are in the
separate `BodyMocap_Test` scene.

## Results

| Check | Result |
|---|---|
| Pure Python suite | 20 tests pass (`python -B tests/run_tests.py`) |
| Blender workflow regressions | 8 tests pass (`blender_workflow_regression.py`) |
| Existing Blender integration suite | Pass; see `_blender_test_result.json` |
| Four source bones → two target bones | Evaluated target rotations match 40° + 40° |
| Two source bones → four target bones | Evaluated target rotations match four 10° rotations |
| Euler-keyed animation | Target receives the expected 20° rotations |
| Mixamo-prefixed arm names | Detected and transferred to different target names |
| Camera pose directions | Correct Z-up conversion and parent compensation, with and without calibration |
| Mirrored/unevenly scaled, rotated armature objects | Correct world-space limb directions |
| Image sequence → MediaPipe → live rig → Action | 613 frames baked; 31 reliable landmarks at final sample |
| Real webcam → live rig → Action | 124 frames baked in the measured fixed run |
| Final webcam coverage check | Up to 27 reliable landmarks; 92 frames recorded; tracking varied between OK, DEGRADED and LOST |
| Sustained full-body webcam capture | **Not verified:** none of 32 samples had all shoulders, elbows, wrists, hips, knees and ankles reliable together |

The image-sequence test uses included person images; it is separate from real
webcam evidence. Recorded webcam motion was mostly upper-body. A new capture
with the entire body visible, including ankles, is still needed to validate
sustained full-body performance. No camera frames were exported as image files.

## Fixes

- Convert camera directions into armature space and solve bone-local rotations
  against rest orientation and the solved parent, including object transforms.
- Read the active rotation representation when retargeting Euler-keyed actions.
- Recognize namespace-prefixed Mixamo and side-prefix names for chain detection.
- Discover already installed per-user OpenCV/MediaPipe dependencies on enable.
- Keep Blender-only executable scripts out of the pure Python unittest runner.
- Make the integration webcam check require an actual frame read and stop
  reporting absent landmarks as a successful body-detection test. Give the
  coarse integration rig its intended bone parents.

The new Blender regressions failed before their corresponding fixes and passed
afterward. Their assertions check evaluated directions/angles, not just keys or
nonzero rotations. Different arbitrary rest rolls, IK/constraint rigs, finger
tracking and root-motion transfer are outside the verified coverage.

## Artifacts

- `../dist/bodymocap.zip` — updated installable add-on.
- `../fixtures/bodymocap_verified.blend` — side-by-side 19-bone and 10-bone
  rigs with the image-sequence Action and its retargeted Action. Press Space
  in the timeline to play. Webcam Actions are retained separately.
- `_workflow_result.json` — eight Blender regression results.
- `_sequence_fixed_result.json` — measured image-sequence capture/bake.
- `_webcam_fixed_result.json` — measured live webcam run after the pose fix.
- `_webcam_coverage_result.json` — final full-body visibility check.

The webcam is stopped. To retry, select `HumanoidRig`, open the BodyMocap
sidebar, choose MediaPipe, leave Video File empty, and start capture while
keeping your whole body in view. Calibrate in a T/A pose before recording.

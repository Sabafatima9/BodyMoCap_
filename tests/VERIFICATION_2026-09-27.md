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

---

# Second pass — version 1.2.0 (same day, later)

Tested in the running Blender 5.2.1 LTS through BlenderMCP (port 9876) with
`scripts/dev_reload_addon.py` hot-reloading the package. Screenshots were taken
from the actual window framebuffer (`screen.screenshot_area`) because the
offscreen viewport render does not run Python draw handlers.

## What changed

- **Camera in the viewport**: `overlay/viewport.py` draws the camera frame
  (with the OpenCV skeleton) as a picture-in-picture in every 3D view plus a
  status strip (tracking state, fps, REC timer, countdown). Mock backend draws
  the 2D skeleton on a dark panel. The tracked body is also drawn as a 3D
  stick figure ("ghost skeleton") anchored to the rig's hips and scaled to the
  rig's torso length.
- **3D solve** (`mapping/apply_pose.py` rewrite): MediaPipe *world* landmarks
  (metres) drive bone directions; hips/spine/chest/neck/head are solved as full
  orientation frames (lateral + up), so yaw/pitch/roll of the body and head are
  reproduced; limbs use absolute directions with parent-follow twist; the hips
  bone gets root translation (image position + apparent body size for depth).
  Calibration now produces a world-correction rotation (camera tilt + stance
  yaw), per-role reference frames, torso length and a root reference.
- **Recording** (`recording/session.py`, `bake/action.py`, `record_ops.py`):
  frame indices follow wall-clock time × scene FPS (takes play back at real
  speed), root locations are stored/baked, keyframes are written live into the
  Action while recording (playhead follows), Stop applies the Action and sets
  the scene range. `bodymocap.quick_record` is the one-button Record / Stop &
  Apply toggle with a 3 s countdown; it starts the camera and auto-maps.
- **Capture worker** (`camera/worker.py`): camera read, MediaPipe inference,
  skeleton overlay and RGBA conversion run on a background thread; the modal
  loop only consumes the newest result. Webcam capture went from ~10 fps to
  ~24 fps (camera-limited); recording throughput ~20 unique frames/s.
- **One-click retarget** (`bodymocap.retarget`): From/To armature pickers with
  fallbacks (capture rig, selection), Action defaults to the source's active
  Action, result is assigned to the target and the timeline framed. Root
  translation is transferred in world space scaled by hip height. Reports the
  number of frames/bones and chain pairing, errors when no chains match.
- Fixed: the OpenCV overlay projected landmarks on the right half of the image
  to wrong pixels; `bodymocap.retarget_transfer` was a Blender Operator
  *subclass* which made `bodymocap.retarget` a silent no-op (now two plain
  classes sharing a function).

## Results

| Check | Result |
|---|---|
| Pure Python suite | 39 tests pass (`python -B tests/run_tests.py`) — new `test_pose_solver.py`, `test_session.py` |
| Blender workflow regressions | 8/8 pass with the new solver (directions, parent compensation, mirrored/scaled objects, 4→2, 2→4, Euler, Mixamo) |
| In-Blender integration (`test_in_blender.py`, background Blender) | 21/21 pass incl. metric world landmarks, root motion, time-indexed recording, one-click retarget |
| Mock capture in GUI | PiP + status strip + ghost skeleton drawn; rig walks; 33 fps loop |
| Webcam capture in GUI | Feed + skeleton in viewport, 24 fps with the worker thread; performer seated/partially visible → DEGRADED, upper body followed |
| Image sequence (`fixtures/pose_seq`) → rig | OK tracking, 29 landmarks, all 18 mapped bones moved, hips translated (root motion), ghost skeleton aligned with rig |
| Quick record on the sequence | Countdown → 247 unique frames in 12.3 s onto frames 1–296 at 24 fps, Hips location curve present, Action assigned, scene range set |
| Live calibration during capture | 2 s, world correction and per-role frames built, root reference valid |
| One-click retarget HumanoidRig → CoarseRig | 200 frames onto 10 bones (spine 5→2, arms 4→2, legs 3→2), Action assigned to target; both rigs raise arms at frame 120 |
| Sustained full-body *webcam* capture | **Still not verified live**: nobody stood fully in view during this session; full-body behaviour was validated with the image sequence only |

Screenshots (mock / fixture sequence only; webcam grabs were not kept, FR-092):
`tests/_shot_mock_win.png`, `tests/_shot_panel.png`, `tests/_shot_seq.png`,
`tests/_shot_rec.png`, `tests/_shot_retarget.png`.

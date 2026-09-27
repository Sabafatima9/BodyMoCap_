# BodyMocap

Blender **4.x / 5.x** add-on (verified on Blender 5.2 LTS) for **camera-based body motion capture**, **joint→armature bone mapping**, **recording straight onto the timeline**, and **N:M cross-armature retargeting** (same logical structure, different bone counts).

## Features

- **Live camera in the 3D Viewport**: the webcam feed with the tracked skeleton is drawn in a corner of every 3D view while capture runs, with tracking state, fps and a REC timer. No need to open an Image Editor (the `BodyMocap_Preview` image is still updated for that).
- **3D tracked skeleton**: the performer's body is drawn as a stick figure in world space, scaled and anchored to the rig, so you can compare your bones with the rig's bones directly.
- **Real 3D pose**: MediaPipe's metric world landmarks drive the solve. Hips, spine, chest, neck and head use full orientation frames, so turning, bending, tilting and head yaw carry into the rig instead of staying on the camera plane. Limbs point exactly where yours point.
- **Root motion**: walk around, crouch or step towards the camera and the hips bone follows (left/right, up/down, depth from apparent body size). Scaled to the rig automatically.
- **One-click Record**: starts the camera, auto-maps the rig, counts down 3 s and records. Keyframes land on the timeline **live** while you perform; **Stop & Apply** assigns the Action and sets the scene range. Frame indices follow real time at the scene FPS, so takes play back at the speed you performed them.
- **One-click Retarget**: pick From / To armatures (or select target + ctrl-select source) and press *Retarget Animation*; different bone counts per chain are remapped proportionally and the result is assigned to the target.
- Guided sidebar ("next step" hint), calibration (camera tilt, facing direction, body scale), smoothing, hold-last / interpolate policies, mock/offline backend for machines without a camera.
- Local-first processing; missing ML deps never crash registration.

## Documentation

| Document | Path |
|----------|------|
| Software Requirements Specification | [`docs/SRS.md`](docs/SRS.md) |
| Project Proposal | [`docs/PROPOSAL.md`](docs/PROPOSAL.md) |
| Install guide | [`INSTALL.md`](INSTALL.md) |
| FR verification checklist | [`docs/VERIFICATION.md`](docs/VERIFICATION.md) |
| Latest verification run | [`tests/VERIFICATION_2026-09-27.md`](tests/VERIFICATION_2026-09-27.md) |

## Quick install

1. Build zip: `python scripts/make_addon_zip.py` → `dist/bodymocap.zip`
2. Blender → Edit → Preferences → Add-ons → Install… → select `bodymocap.zip`
3. Enable **BodyMocap** (category: Animation)
4. Optional deps (for live camera + MediaPipe): see [`INSTALL.md`](INSTALL.md)

Without OpenCV/MediaPipe the add-on still enables; use **Mock / Offline** backend for mapping, record (synthetic), bake/retarget logic testing.

## Workflow (the short version)

1. Select your humanoid **Armature**. Sidebar **N → BodyMocap**.
2. Set **Backend** to *MediaPipe* (Camera & Display panel) if you have a webcam.
3. Press **Record**. The camera view appears in the viewport, the rig starts following you, and after the countdown keyframes appear on the timeline.
4. Press **Stop & Apply**. Press **Space** to play the take.
5. Optional: pick another rig under **Retarget to another rig → To** and press **Retarget Animation**.

Tips: stand so your whole body is in view; press **Calibrate** while holding a T-pose facing the camera for best 3D results (it removes camera tilt and your stance yaw); tune **Smoothing** under *Tracking* if the motion is jittery.

## Tests

```bash
python tests/run_tests.py                      # pure Python (no Blender)
blender --background fixtures/bodymocap_test.blend --python tests/test_in_blender.py
```

Development helpers (need the BlenderMCP add-on server on port 9876):

```bash
python scripts/dev_reload_addon.py             # copy bodymocap/ into Blender's add-ons and hot-reload
python scripts/blender_mcp_client.py -c "import bpy; print(bpy.app.version_string)"
```

## Package layout

Installable package is `bodymocap/` (must remain the zip root folder name).

## License

Prototype project code — align redistribution with chosen pose-backend licenses before public release.

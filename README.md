# BodyMocap

Blender **4.x / 5.x** add-on (verified on Blender 5.2 LTS) for **camera-based body motion capture**, **joint→armature bone mapping**, **recording/bake to Actions**, and **N:M cross-armature retargeting** (same logical structure, different bone counts).

## Features (MVP)

- Webcam capture via OpenCV (device index **or video file / image sequence** for testing) with live Image preview + skeleton overlay
- MediaPipe Pose backend (supports both 0.x `solutions` and 1.x `tasks`/PoseLandmarker APIs; a `pose_landmarker_full.task` model ships in `bodymocap/assets/`) and **Mock/offline** backend for no-camera workflows
- T-pose / A-pose calibration; mirror, subject scale/distance
- Auto + manual bone mapping with JSON presets and quality report
- Record / pause / resume / discard; bake to Action; one-click Apply (action or NLA)
- Proportional chain retargeting (validated **4→2** and **2→4** arm cases)
- Local-first processing; missing ML deps do not crash registration

## Documentation

| Document | Path |
|----------|------|
| Software Requirements Specification | [`docs/SRS.md`](docs/SRS.md) |
| Project Proposal | [`docs/PROPOSAL.md`](docs/PROPOSAL.md) |
| Install guide | [`INSTALL.md`](INSTALL.md) |
| FR verification checklist | [`docs/VERIFICATION.md`](docs/VERIFICATION.md) |

## Quick install

1. Build zip: `python scripts/make_addon_zip.py` → `dist/bodymocap.zip`
2. Blender → Edit → Preferences → Add-ons → Install… → select `bodymocap.zip`
3. Enable **BodyMocap** (category: Animation)
4. Optional deps (for live camera + MediaPipe): see [`INSTALL.md`](INSTALL.md)

Without OpenCV/MediaPipe the add-on still enables; use **Mock / Offline** backend for mapping, record (synthetic), bake/retarget logic testing.

## Workflow

1. Select a humanoid **Armature**
2. Sidebar **N-panel → BodyMocap**: Refresh dependencies
3. Choose backend (**Mock** or **MediaPipe**), Start capture
4. **Calibrate** while holding T/A pose
5. **Auto-Map** bones; refine list; Save preset if desired
6. **Rec** → perform → **Stop** → **Bake to Action** → **Apply Action**
7. Optional: set Source/Target armatures → **Retarget Action**

## Tests (no Blender)

```bash
cd blender-mocap-addon
python tests/run_tests.py
```

## Package layout

Installable package is `bodymocap/` (must remain the zip root folder name).

## License

Prototype project code — align redistribution with chosen pose-backend licenses before public release.

# Software Requirements Specification (SRS)

**Product:** BodyMocap  
**Document Title:** Software Requirements Specification — BodyMocap Blender Add-on  
**Version:** 0.1  
**Date:** 2026-09-18  
**Status:** Draft  
**Audience:** Technical stakeholders, developers, collaborators

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) defines the functional and non-functional requirements for **BodyMocap**, a Blender add-on that captures human body motion from a live camera feed, maps detected joints to Blender armature bones, records motion, and bakes the result into Blender animation that the user can apply with one click.

This document is the authoritative requirements baseline for design, implementation, verification, and acceptance of version 1.0 (MVP) and selected Phase 2 capabilities called out herein.

### 1.2 Scope

**In scope (v1):**

- Blender add-on packaging, install, and enable/disable lifecycle
- Webcam (and optionally depth-camera) capture UX within Blender
- Single-person body pose estimation and on-screen skeleton overlay
- Automatic and manual mapping between detected joints and armature bones
- Motion recording sessions and bake to Blender Action / keyframes
- One-click apply of recorded animation to a target armature
- Cross-armature retargeting between structures with the same logical hierarchy but different bone counts (N:M bone-chain remapping)
- Local-first processing preference; robustness requirements for lighting and motion variation
- Error handling, logging, and proposed accuracy / performance targets

**Out of scope (v1):** See Section 10.

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|------------|
| **Blender** | Open-source 3D creation suite; host application for the add-on |
| **Add-on** | Python package loaded by Blender that extends the UI and operators |
| **Armature** | Blender object consisting of bones used to deform meshes (rig) |
| **Bone** | Named transform node in an armature hierarchy |
| **Pose** | Current transforms of armature bones (pose mode) |
| **Rest pose** | Default / bind pose of the armature (often T-pose or A-pose) |
| **Action** | Blender datablock storing animation keyframes for an object |
| **Mocap** | Motion capture — recording real-world movement for animation |
| **Pose estimation** | ML / CV process that detects human joint landmarks from images/video |
| **MediaPipe** | Google’s on-device ML framework; Pose landmark model is a candidate backend |
| **OpenPose** | Multi-person pose estimation system; alternative candidate backend |
| **Retargeting** | Transferring animation from one skeleton to another with different proportions or topology |
| **Bone mapping** | Correspondence between camera-detected joints and armature bones |
| **N:M chain remapping** | Mapping a bone chain of length N to a chain of length M (e.g., 4→2 arm bones) |
| **IK / FK** | Inverse / Forward Kinematics |
| **Landmark** | Detected joint position (typically 2D image or 3D world/normalized coords) |
| **Confidence** | Per-landmark or per-frame score from the pose estimator |
| **bpy** | Blender’s Python API module |
| **MVP** | Minimum Viable Product (v1) |
| **NFR** | Non-functional requirement |
| **FR** | Functional requirement |

### 1.4 References

- Blender 4.x Manual — Python API / Animation / Armatures (official Blender documentation)
- Candidate pose libraries: MediaPipe Pose, OpenPose, or equivalent (selection in Section 8)
- This project’s companion document: `PROPOSAL.md`

*No fabricated papers or benchmarks are cited. Accuracy numbers in this SRS are proposed targets pending validation.*

### 1.5 Overview

Section 2 describes the product context. Section 3 lists system features as numbered requirements. Sections 4–9 cover interfaces, constraints, assumptions, acceptance, out-of-scope items, and risks.

---

## 2. Overall Description

### 2.1 Product Perspective

BodyMocap is a **Blender add-on**, not a standalone application. It runs inside Blender’s process, uses Blender’s UI (panels/operators), and writes animation into standard Blender Actions so results remain editable without the add-on after bake.

High-level data flow:

```
Camera → Pose estimation → Detected skeleton → Bone mapper / Retargeter → Blender armature pose → Action bake
```

A second pipeline path supports **armature-to-armature** remapping (source Action or live mapped pose → N:M chain mapper → target armature).

### 2.2 User Classes and Characteristics

| User class | Description | Needs |
|------------|-------------|--------|
| **Animator / Rigger** | Creates or uses character armatures; wants faster body blocking | Reliable mapping, one-click apply, editable Actions |
| **Technical artist** | Maintains rigs, may adjust bone names and hierarchy | Manual mapping override, exportable mapping presets |
| **Indie / student user** | Limited mocap budget; webcam-based workflow | Simple install, clear UX, local processing |
| **Developer / integrator** | Extends or validates the add-on | Documented operators, mapping API hooks, logs |

Primary persona for v1: single animator with a named humanoid armature and a webcam.

### 2.3 Operating Environment

| Aspect | Requirement |
|--------|-------------|
| Host | Blender **4.x** (target; exact minor version pinned in release notes) |
| OS | Windows, macOS, Linux (desktop) |
| Camera | USB webcam or built-in camera; optional depth camera if backend supports it |
| Runtime | Blender-bundled Python; optional native ML runtime / wheels compatible with that Python |
| GPU | Optional acceleration; CPU fallback shall be supported for MVP where feasible |
| Display | Blender 3D Viewport + add-on panel (N-panel or Properties) |

### 2.4 Product Functions (Summary)

1. Install and enable the add-on  
2. Open / spawn camera preview and (optional) calibration  
3. Detect human body and visualize skeleton overlay  
4. Auto-map and manually refine joint→bone correspondence  
5. Record motion; bake to Action/keyframes  
6. One-click apply animation to the selected armature  
7. Remap motion between armatures with same structure, different bone counts  
8. Handle detection failures, privacy, and performance within stated targets  

### 2.5 Assumptions and Dependencies

See Section 8. Summary assumptions:

- User has a roughly humanoid armature with identifiable limb chains.
- User can provide or adopt a known rest pose (T-pose / A-pose) for calibration.
- Single person is visible and dominant in frame for v1.
- Network is **not** required for core capture when using an on-device pose backend.

### 2.6 Apportioning of Requirements

- **MVP (v1):** Camera, detection, mapping, record, bake, apply, basic N:M chain remap, local processing, robustness tests documented.
- **Phase 2:** Depth camera refinement, richer hand/face (if demanded later), multi-person, cloud offload (explicitly not preferred), advanced IK solvers, preset marketplace.

---

## 3. System Features and Requirements

Requirements use **shall** for mandatory MVP behavior unless marked **Phase 2** or **proposed target**.

### 3.1 Installation and Lifecycle

**FR-001** The system shall be distributable as a standard Blender add-on package (zip or multi-file package with `__init__.py` and `bl_info`).

**FR-002** The user shall be able to install, enable, disable, and uninstall the add-on via Blender Preferences → Add-ons.

**FR-003** On enable, the add-on shall register UI panels, operators, and properties without crashing Blender if optional ML dependencies are missing; instead it shall show a clear dependency status message.

**FR-004** The add-on shall declare Blender version compatibility in `bl_info` and refuse silent operation on unsupported major versions (warn and disable operators).

### 3.2 Camera Spawn and Calibration UX

**FR-010** The system shall provide an operator to start a camera feed from a user-selectable device index (default: 0).

**FR-011** The system shall display a live preview (Blender image editor, viewport overlay, or dedicated preview pane) while the session is active.

**FR-012** The system shall provide an operator to stop the camera feed and release the device.

**FR-013** The system shall support a **calibration step** in which the user holds a rest pose (T-pose or A-pose, user-selectable) for a configurable duration (proposed default: 1–3 seconds).

**FR-014** During calibration, the system shall capture a reference skeleton pose used to align detection space to armature rest pose (scale, facing direction, and optional floor plane).

**FR-015** The system shall allow the user to flip horizontal mirroring (selfie vs. facing camera) and to set approximate camera FOV / subject distance for scale estimation when depth is unavailable.

**FR-016** If no camera device is available, the system shall fail with a user-visible error and shall not hang Blender’s UI thread indefinitely.

### 3.3 Body Detection

**FR-020** The system shall detect a single human body pose from the active camera frames using the selected pose-estimation backend.

**FR-021** The system shall produce a time-sequenced set of joint landmarks (2D and/or 3D, backend-dependent) with per-landmark confidence scores when the backend provides them.

**FR-022** The system shall apply a configurable **minimum confidence threshold**; landmarks below threshold shall be marked invalid for that frame.

**FR-023** When confidence is low or the body is lost, the system shall (configurable): hold last valid pose, interpolate briefly, or drop recording samples — and shall indicate status in the UI (e.g., “Tracking OK / Degraded / Lost”).

**FR-024** The system shall process frames locally by default (no mandatory cloud round-trip for pose inference).

### 3.4 Skeleton Visualization Overlay

**FR-030** The system shall draw a skeleton overlay (joints + bones) on the camera preview and/or 3D Viewport corresponding to the current detection.

**FR-031** The overlay shall visually distinguish high-confidence vs. low-confidence joints (e.g., color or opacity).

**FR-032** The user shall be able to toggle the overlay on/off without stopping the camera.

### 3.5 Bone Mapping (Camera → Armature) — Critical Feature

**FR-040** The system shall support **automatic mapping** from a standard detected joint set (e.g., MediaPipe-style body landmarks) to bones of a selected Blender armature using name heuristics and hierarchy templates (humanoid preset).

**FR-041** The system shall support **manual mapping** via a UI list: detected joint ↔ armature bone, with add/remove/clear.

**FR-042** Mapping presets shall be saveable and loadable (JSON or Blender Text / custom property) per armature or as named profiles.

**FR-043** The system shall support hierarchical mapping: parent–child relationships in the detected skeleton shall inform which armature bones receive which transforms.

**FR-044** The mapping pipeline shall account for rest-pose calibration (FR-013–FR-014) so that zero-motion in calibrated rest yields near-rest armature pose.

**FR-045** The system shall expose mapping quality feedback: unmapped required joints, duplicate mappings, and bones with no source.

**FR-046** Mapping accuracy is the **most critical** product requirement: after calibration and mapping, under controlled conditions defined in the test plan, proposed target is that major limb end-effectors (wrists, ankles, head) remain visually plausible relative to the performer, with quantitative checks defined in Section 9 (proposed targets, not claimed benchmarks).

#### Hard problem notes (normative design intent)

- **Correspondence:** Prefer a template-based hierarchical map (hips → spine → neck → head; shoulders → arms; hips → legs) over naive nearest-name matching alone.
- **IK/FK:** MVP may drive FK bone rotations derived from bone directions between landmarks; Phase 2 may add IK targets at wrists/ankles/head for stability.
- **Missing landmarks:** Do not snap bones to origin; use hold/interpolate policy (FR-023).

### 3.6 Recording Session

**FR-050** The user shall be able to start, pause, resume, and stop a recording session while tracking is active.

**FR-051** During recording, the system shall store per-frame mapped bone transforms (or equivalent joint data + mapping id) with timestamps or frame indices synced to a chosen Blender FPS.

**FR-052** The system shall allow discarding the current take without baking.

**FR-053** The system shall warn if tracking status is Degraded/Lost for more than a configurable fraction of the take (proposed default: 15% of frames).

### 3.7 Bake to Action / Keyframes and One-Click Apply

**FR-060** The system shall bake a completed take into a Blender **Action** with keyframes on the mapped pose bones (location/rotation as applicable; scale typically locked unless configured).

**FR-061** The user shall be able to set Action name, start frame, and whether to overwrite or create a new Action.

**FR-062** The system shall provide a **one-click Apply** operator that assigns the baked Action to the selected armature (or applies as NLA strip — configurable) so the character plays the recorded motion.

**FR-063** After bake, the resulting animation shall remain editable in Blender’s Graph Editor / Dope Sheet without requiring BodyMocap to be running (data lives in standard Blender datablocks).

**FR-064** Optional: the system may provide light post-filters (proposed Phase 2 or MVP toggle): Gaussian smoothing on rotations, foot-contact lock — clearly labeled as optional.

### 3.8 Cross-Armature Retargeting (N:M Bone Counts) — Second Major Feature

**FR-070** The system shall retarget animation from a **source armature** to a **target armature** that share the same logical structure (humanoid chains) but may differ in bone counts per chain (example: source upper-arm→forearm→hand with finer spine vs. target with fewer bones).

**FR-071** The system shall allow the user to define **chain pairs** (e.g., Source Arm.L chain ↔ Target Arm.L chain) either automatically via hierarchy detection or manually.

**FR-072** For a chain of **N** bones mapped to **M** bones (N ≠ M), the system shall compute intermediate transforms using an explicit remapping strategy:

1. **Segment aggregation (N > M):** Partition the source chain into M contiguous groups by proportional length along the chain; aggregate each group’s delta rotation (e.g., swing decomposition or cumulative quaternion slerp) into one target bone.  
2. **Segment splitting / interpolation (N < M):** Distribute source bone motion across multiple target bones by proportional chain parameterization (arc-length or bone-length weights), inserting interpolated orientations so the target end-effector approximates the source end-effector direction and optional position.  
3. **Weighted blending:** When landmarks or bone tips define end-effectors, blend toward end-effector constraints with configurable weights.

**FR-073** Example normative behavior — **4→2 arm remap:** Given source bones `[shoulder→upper→forearm→hand]` (or four arm segments) and target `[upper_arm, forearm]`, the system shall aggregate the proximal two source segments into `upper_arm` and the distal two into `forearm` (or by measured rest-pose lengths if unequal), preserving approximate elbow location along the chain and wrist/end direction within proposed error budgets (Section 9).

**FR-074** The system shall support the inverse **2→4** case via proportional splitting (FR-072.2).

**FR-075** Retargeting shall use rest-pose alignment between source and target (T/A-pose calibration or bind-pose matrices) before applying motion deltas.

**FR-076** Retargeting output shall be writable as a new Action on the target armature (same bake/apply path as FR-060–FR-062).

### 3.9 Error Handling and Diagnostics

**FR-080** Operators shall report failures via Blender reports (`{'ERROR'}` / `{'WARNING'}`) with actionable text.

**FR-081** The system shall log session diagnostics (device index, backend name, average FPS, % low-confidence frames) to a user-accessible log or console output.

**FR-082** Dependency import failures shall not crash Blender on start-up registration beyond disabling dependent operators.

### 3.10 Privacy

**FR-090** Pose processing shall default to **on-device / local** inference.

**FR-091** The system shall not upload camera frames to a remote service unless the user explicitly enables an optional remote backend (Phase 2; disabled by default) and confirms a clear consent prompt.

**FR-092** The system shall not persist raw video unless the user explicitly enables “save debug video”; default recording stores skeleton / bone transforms only.

### 3.11 Non-Functional Requirements

**NFR-001 Performance (proposed targets):** On a reference mid-range laptop CPU, live preview + pose + overlay shall sustain a proposed target of ≥ 15 FPS; with GPU acceleration where available, proposed target ≥ 24 FPS. Exact hardware baselines to be recorded in the test report.

**NFR-002 Latency (proposed target):** End-to-end camera frame → visible armature update ≤ 150 ms median under reference conditions (proposed).

**NFR-003 Robustness — lighting:** Detection shall be validated under at least: bright daylight, indoor office lighting, dim indoor, and mixed backlight (see Section 9). Degradation shall be indicated per FR-023 rather than silent corruption.

**NFR-004 Robustness — motion:** Validation shall include slow movement, walking in place, arm reaches, torso twists, and rapid gestures; extreme sports motion is Phase 2 stretch.

**NFR-005 Usability:** A new user with Blender familiarity shall complete “enable → calibrate → map → record 5 s → bake → apply” with documentation only (no developer assistance) in a usability dry-run.

**NFR-006 Compatibility:** Core operators shall run on Windows, macOS, and Linux Blender 4.x builds listed in the release matrix.

**NFR-007 Maintainability:** Mapping and retargeting logic shall be unit-testable outside interactive Blender where feasible (pure math modules).

**NFR-008 Security / supply chain:** Third-party wheels shall be pinned and documented; no silent download of binaries without user action.

---

## 4. External Interfaces

### 4.1 Blender Python API (`bpy`)

- Armature / PoseBone read-write, Action / FCurve / keyframe insertion  
- UI: `bpy.types.Panel`, `Operator`, `PropertyGroup`  
- Timer or modal operator for camera loop (must remain UI-responsive)

### 4.2 Camera Input

- Device enumeration and frame grab via OpenCV, Blender video sequence tools, or platform APIs — implementation choice constrained by Blender’s Python environment  
- Frame format: RGB/BGR arrays at configurable resolution (e.g., 640×480, 1280×720)

### 4.3 Pose Estimation Runtime

- Optional native library / Python wheel (MediaPipe, OpenPose bindings, ONNX Runtime, etc.)  
- Interface abstraction: `PoseBackend.infer(frame) → Landmarks`

### 4.4 User Interface

- Add-on panel in 3D Viewport sidebar (N-panel) and/or Properties  
- Preview window for camera + overlay  
- Mapping editor list UI

### 4.5 File / Data Interfaces

- Mapping preset files (JSON)  
- Optional debug image/video export (user-initiated)  
- Standard `.blend` Action datablocks (primary output)

---

## 5. Constraints

**C-001** Packaging must follow Blender add-on conventions; no requirement for a separate installer.exe beyond optional helper for ML wheels.

**C-002** Python version is whatever Blender 4.x ships; external packages must match that ABI.

**C-003** GPU acceleration is optional; CPU path required for MVP feasibility on machines without discrete GPU.

**C-004** Real-time constraints must not freeze Blender; heavy work may use modal timers, background threads with thread-safe marshalling back to main thread for `bpy` calls (Blender API is not generally thread-safe).

**C-005** Licensing of pose backends must be compatible with the project’s intended distribution model (to be confirmed before release).

---

## 6. Assumptions and Dependencies

### 6.1 Pose Backend Options

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **MediaPipe Pose** | On-device, relatively easy Python integration, strong single-person body landmarks | Landmark set / model evolution; packaging into Blender Python can be non-trivial | **Recommended default for MVP** |
| **OpenPose** | Mature, research-proven | Heavier, multi-person oriented, harder packaging | Alternative if MediaPipe packaging fails |
| **ONNX / custom model** | Full control, tunable | Higher ML ops cost | Phase 2 if accuracy gaps remain |
| **Depth camera SDK** (RealSense, etc.) | Better 3D scale | Extra hardware | Optional Phase 2 |

**Assumption A-001:** A single recommended backend will be selected in prototype phase; the architecture shall isolate backends behind an interface (Section 4.3).

**Assumption A-002:** Users can achieve a clear view of the full body (or at least torso + limbs needed for their take).

**Assumption A-003:** Target armatures are roughly humanoid; quadrupeds / non-humanoids are out of scope for v1.

---

## 7. Design Intent for Hard Problems (Informative + Normative Hooks)

### 7.1 Bone Correspondence / Retargeting Algorithms

Approaches the implementation **shall** support or evaluate:

1. **Hierarchical template mapping** — fixed humanoid graph aligned by semantic roles (pelvis, spine, head, limbs).  
2. **Proportional chain mapping** — parameterize each limb by normalized arc length 0→1; sample source pose along chain; write to target bones at their rest-length parameters (enables N:M).  
3. **IK/FK hybrid (Phase 2 preferred)** — FK for spine; IK for limbs using wrist/ankle targets derived from landmarks.

### 7.2 Rest Pose Calibration (T-pose / A-pose)

- User selects expected rest style.  
- System averages landmarks over calibration window.  
- Computes rotation offset from detected bone directions to armature rest bone directions (per mapped bone or per chain).  
- Stores scale factor from detected hip–shoulder or hip–ankle length vs. armature.

### 7.3 Confidence Thresholds

- Global and per-joint thresholds (proposed defaults: 0.5–0.7 depending on backend scale).  
- Hysteresis to avoid flicker (e.g., require N consecutive low frames before “Lost”).  
- Recording policy documented in UI.

### 7.4 4→2 Arm Remapping (Worked Intent)

Rest-pose lengths: source segments `L1..L4`, target `T1, T2`.

- Assign source parameter intervals `[0, a)` → target bone 1, `[a, 1]` → target bone 2, where `a = T1 / (T1+T2)` (or equal split if lengths unknown).  
- Aggregate source rotations in each interval via quaternion averaging / swing extraction relative to parent.  
- Verify end-effector direction error against proposed target (Section 9).

---

## 8. Acceptance Criteria and Verification Methods

| Feature | Acceptance criteria | Verification |
|---------|---------------------|--------------|
| Install | Enables on Blender 4.x reference builds without crash | Manual install matrix (Win/macOS/Linux) |
| Camera | Preview starts/stops; error if no device | Manual + device unplug test |
| Detection | Skeleton appears for standing person in office light | Manual + recorded fixture videos |
| Mapping | Auto-map + manual edit + preset round-trip | Unit tests for preset I/O; manual map check |
| Record/Bake | 5–30 s take becomes Action with keys | Manual; keyframe count sanity check |
| One-click apply | Character plays motion in viewport | Manual |
| Mapping accuracy | Proposed target: after calibration, wrist/ankle screen-space or bone-direction error within agreed thresholds on fixture set (thresholds set during prototype; labeled proposed until measured) | Scripted replay on fixture clips |
| Lighting/motion robustness | Test matrix in Section 9 executed; results logged; no crash; degraded state visible | Formal test report |
| N:M retarget | 4→2 and 2→4 arm fixtures produce plausible motion; end-effector error within proposed budget | Automated math tests + visual review |
| Privacy | Default path does not open network sockets for inference | Code review + optional runtime check |

---

## 9. Test Plan Requirements (Normative for Validation)

**TR-001** Lighting conditions (minimum): bright diffuse, indoor ceiling, dim indoor, strong backlight.

**TR-002** Motion types (minimum): idle, walk-in-place, reach high/low, torso twist, sit-to-stand (if framing allows), rapid wave.

**TR-003** Armature complexity (minimum): simple 15–20 bone humanoid; production-like humanoid with multi-bone spine and 4-bone arms; reduced 2-bone arms for remap tests.

**TR-004** Results shall be recorded in a test report (pass/fail per case, notes on failure modes). Accuracy numbers published only as measured or clearly marked proposed targets.

---

## 10. Out of Scope for v1

- Multi-person tracking and identity switching  
- Facial mocap / blendshape driving  
- High-fidelity hand mocap (fingertips) as a core promise (optional coarse hand if backend provides it — not acceptance-critical)  
- Mandatory cloud processing  
- Marker-based optical mocap suit pipelines  
- Non-humanoid creatures  
- Automatic mesh generation / auto-rigging from video  
- Mobile (iOS/Android) Blender variants  
- Guaranteed sub-centimeter metrical accuracy without depth hardware  

---

## 11. Risks and Open Questions

| ID | Risk / question | Impact | Notes |
|----|-----------------|--------|-------|
| R-001 | Packaging MediaPipe (or similar) into Blender’s Python is fragile across OS | High | Spike early; abstract backend |
| R-002 | Monocular 3D depth ambiguity (scale, foot skate) | High | Calibration + optional Phase 2 depth |
| R-003 | Bone name diversity across rigs breaks auto-map | Medium | Strong manual map + presets |
| R-004 | N:M remap quality on stylized proportions | Medium | Proportional chains + visual fixtures |
| R-005 | UI thread performance / Blender freezes | Medium | Modal design, resolution limits |
| R-006 | Backend license compatibility | Medium | Legal review before public release |
| Q-001 | Exact landmark set and naming for the chosen backend? | — | Decide in prototype |
| Q-002 | FK-only vs. early IK for limbs in MVP? | — | Prefer FK MVP; IK Phase 2 unless spike shows necessity |
| Q-003 | Minimum Blender minor version (4.0 vs 4.2+)? | — | Pin after dependency test |
| Q-004 | Do investors/collaborators require offline demo reel criteria beyond SRS? | — | Align success metrics in PROPOSAL |

---

## 12. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-09-18 | BodyMocap project | Initial draft SRS |

---

*End of SRS*

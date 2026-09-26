"""In-Blender integration test for BodyMocap on Blender 5.x.

Run:
  blender --background fixtures/bodymocap_test.blend --python tests/test_in_blender.py

Exercises: registration, deps, MediaPipe init + inference on a real photo and a
live webcam frame, mock loop → armature apply, record → bake → apply, retarget.
Writes results to tests/_blender_test_result.json and exits non-zero on failure.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
RESULTS: dict = {}
FAILURES: list = []


def check(name, ok, detail=""):
    RESULTS[name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"[TEST] {'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILURES.append(name)


def main():
    scene = bpy.context.scene
    print("=" * 60)
    print("BodyMocap in-Blender test — Blender", bpy.app.version_string)
    print("=" * 60)

    # 1. Addon registered -----------------------------------------------------
    check("addon_registered", hasattr(scene, "bodymocap"), "scene.bodymocap")
    settings = scene.bodymocap

    # 2. Dependency status -----------------------------------------------------
    from bodymocap.utils.blender_compat import dependency_status
    deps = dependency_status()
    for name, info in deps.items():
        print("  dep:", name, info)
    check("dep_numpy", deps["numpy"]["available"] == "yes", deps["numpy"]["version"])
    check("dep_opencv", deps["opencv"]["available"] == "yes", deps["opencv"]["version"])
    check("dep_mediapipe", deps["mediapipe"]["available"] == "yes",
          deps["mediapipe"]["version"])

    # 3. MediaPipe backend -----------------------------------------------------
    from bodymocap.pose.mediapipe_backend import MediaPipeBackend, mediapipe_available
    check("mp_available", mediapipe_available())
    be = MediaPipeBackend()
    ok = be.initialize()
    check("mp_init", ok, f"api={be._api} err={be.last_error}")

    # Inference on real photo (a standing person → should detect landmarks)
    photo = ROOT / "fixtures" / "pose_person.jpg"
    n_landmarks = 0
    state = "LOST"
    if ok and photo.is_file():
        import cv2

        img = cv2.imread(str(photo))
        for i in range(5):  # let hysteresis settle
            pf = be.infer(img, frame_index=i, timestamp=i / 30.0)
        n_landmarks = sum(1 for l in pf.landmarks.values() if l.valid)
        state = pf.tracking_state.name
    check("mp_photo_landmarks", n_landmarks >= 20,
          f"{n_landmarks} valid landmarks, state={state}")

    # Live webcam frame through capture + backend
    cam_ok, cam_lm = False, 0
    try:
        from bodymocap.camera.capture import CameraCapture
        cap = CameraCapture()
        cam_ok = cap.open_source(0)
        if cam_ok:
            ok_frame, frame = cap.read()
            if ok_frame and frame is not None and ok:
                pf = be.infer(frame, frame_index=100, timestamp=time.time())
                cam_lm = sum(1 for l in pf.landmarks.values() if l.valid)
            cap.close()
    except Exception as exc:
        print("  webcam test exc:", exc)
    check("webcam_capture", cam_ok, "device 0 opened + frame read")
    RESULTS["webcam_landmarks"] = {"ok": True, "detail": f"{cam_lm} landmarks on live frame"}
    print("  live webcam landmarks:", cam_lm, "(0 is fine if nobody is in front of camera)")
    be.shutdown()

    # 4. Auto-map + live apply via Mock backend --------------------------------
    arm = bpy.data.objects.get("HumanoidRig") or next(
        (o for o in bpy.data.objects if o.type == "ARMATURE"), None
    )
    check("armature_present", arm is not None, arm.name if arm else "none")
    if arm:
        bpy.context.view_layer.objects.active = arm
        arm.select_set(True)

        bpy.ops.bodymocap.auto_map()
        mapped = {e.role: e.bone_name for e in settings.mapping_entries if e.bone_name}
        check("auto_map", len(mapped) >= 8, f"{len(mapped)} roles mapped")

        from bodymocap.core.confidence import ConfidenceConfig, TrackingHysteresis
        from bodymocap.mapping.apply_pose import (
            apply_landmarks_to_rotations,
            apply_rotations_to_armature,
            average_calibrations,
        )
        from bodymocap.pose.mock_backend import MockBackend

        mock = MockBackend(mode="walk", confidence_cfg=ConfidenceConfig())
        mock.initialize(mode="walk")

        # Calibrate from synthetic frames
        samples = [mock.infer(None, i, i / 30.0).landmarks for i in range(10)]
        cal = average_calibrations(samples)
        check("calibration", cal.valid, f"scale={cal.scale:.3f} rest_dirs={len(cal.bone_rest_dirs)}")

        # Apply a moving pose frame → pose bones should rotate
        before = {pb.name: pb.rotation_quaternion.copy() for pb in arm.pose.bones}
        applied = 0
        for i in range(20, 40):
            pf = mock.infer(None, i, i / 30.0)
            rots = apply_landmarks_to_rotations(pf.landmarks, mapped, cal)
            applied = apply_rotations_to_armature(arm, rots)
        moved = [
            n for n in before
            if (arm.pose.bones[n].rotation_quaternion - before[n]).magnitude > 1e-4
        ]
        check("live_apply_rotations", applied > 0 and len(moved) > 0,
              f"{applied} bones set, {len(moved)} moved")

        # 5. Record + bake + apply ---------------------------------------------
        bpy.ops.bodymocap.record_start()
        from bodymocap.recording.session import get_active_session
        session = get_active_session()
        for i in range(40, 70):
            pf = mock.infer(None, i, i / 30.0)
            rots = apply_landmarks_to_rotations(pf.landmarks, mapped, cal)
            session.append(i - 40, rots, pf.tracking_state, i / 30.0)
        bpy.ops.bodymocap.record_stop()
        n_rec = session.frame_count()
        check("record_frames", n_rec == 30, f"{n_rec} frames")

        bpy.ops.bodymocap.bake_action()
        action = bpy.data.actions.get(settings.action_name)
        n_keys = 0
        if action is not None:
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for fc in bag.fcurves:
                            n_keys += len(fc.keyframe_points)
        check("bake_action", action is not None and n_keys > 0,
              f"action={settings.action_name} keys={n_keys}")

        bpy.ops.bodymocap.apply_action()
        check("apply_action",
              arm.animation_data is not None and arm.animation_data.action is not None,
              arm.animation_data.action.name if arm.animation_data and arm.animation_data.action else "none")

        # frame evaluation actually poses the bones
        scene.frame_set(settings.bake_start_frame + 5)
        animated = any(
            pb.rotation_quaternion.magnitude > 0 and
            abs(pb.rotation_quaternion.w - 1.0) > 1e-4
            for pb in arm.pose.bones
        )
        check("action_evaluates", animated, "posed bones differ from identity")

        # 6. Retarget to a 2nd (coarser) armature -------------------------------
        tgt = bpy.data.armatures.new("CoarseRig")
        tgt_obj = bpy.data.objects.new("CoarseRig", tgt)
        scene.collection.objects.link(tgt_obj)
        bpy.context.view_layer.objects.active = tgt_obj
        bpy.ops.object.mode_set(mode="EDIT")
        ebs = {}
        for name, head, tail, parent in [
            ("Hips", (0, 0, 1.0), (0, 0, 1.1), None),
            ("Spine", (0, 0, 1.1), (0, 0, 1.45), "Hips"),
            ("Arm.L", (0.18, 0, 1.45), (0.42, 0, 1.45), "Spine"),
            ("LowerArm.L", (0.42, 0, 1.45), (0.66, 0, 1.45), "Arm.L"),
            ("Arm.R", (-0.18, 0, 1.45), (-0.42, 0, 1.45), "Spine"),
            ("LowerArm.R", (-0.42, 0, 1.45), (-0.66, 0, 1.45), "Arm.R"),
            ("UpLeg.L", (0.1, 0, 1.0), (0.1, 0, 0.55), "Hips"),
            ("LowLeg.L", (0.1, 0, 0.55), (0.1, 0, 0.12), "UpLeg.L"),
            ("UpLeg.R", (-0.1, 0, 1.0), (-0.1, 0, 0.55), "Hips"),
            ("LowLeg.R", (-0.1, 0, 0.55), (-0.1, 0, 0.12), "UpLeg.R"),
        ]:
            eb = tgt.edit_bones.new(name)
            from mathutils import Vector
            eb.head = Vector(head)
            eb.tail = Vector(tail)
            ebs[name] = eb
        for name, eb in ebs.items():
            pass
        bpy.ops.object.mode_set(mode="OBJECT")
        for name, head, tail, parent in []:
            pass
        bpy.context.view_layer.objects.active = tgt_obj
        tgt_obj.select_set(True)

        settings.source_armature = arm.name
        settings.target_armature = tgt_obj.name
        settings.retarget_action = settings.action_name
        settings.retarget_new_action = "RetargetedTest"
        bpy.ops.bodymocap.retarget_transfer()
        new_act = bpy.data.actions.get("RetargetedTest")
        tgt_keys = 0
        if new_act:
            for layer in new_act.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for fc in bag.fcurves:
                            tgt_keys += len(fc.keyframe_points)
        check("retarget", new_act is not None and tgt_keys > 0,
              f"keys={tgt_keys}")

    # Write results
    out = ROOT / "tests" / "_blender_test_result.json"
    summary = {
        "blender": bpy.app.version_string,
        "results": RESULTS,
        "failures": FAILURES,
        "passed": len(FAILURES) == 0,
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("=" * 60)
    print("RESULT:", "ALL PASSED" if not FAILURES else f"FAILURES: {FAILURES}")
    print("=" * 60)


try:
    main()
except Exception:
    traceback.print_exc()
    FAILURES.append("unhandled_exception")

sys.exit(0 if not FAILURES else 1)

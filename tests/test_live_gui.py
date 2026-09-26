"""Live GUI test: run the real modal capture loop with MediaPipe + webcam.

Run (GUI Blender, stays open ~RUN_SECONDS then quits):
  blender fixtures/bodymocap_test.blend --python tests/test_live_gui.py

Writes tests/_live_test_result.json.
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
RUN_SECONDS = 12.0
_start = None
_done = False


def _tick():
    global _start, _done
    scene = bpy.context.scene
    settings = scene.bodymocap
    if _start is None:
        _start = time.time()
        print("[LIVE] capture running...")

    elapsed = time.time() - _start
    if elapsed >= RUN_SECONDS and not _done:
        _done = True
        _finish(scene, settings)
        return None  # unregister timer
    return 0.5


def _finish(scene, settings):
    from bodymocap.operators.camera_ops import get_last_landmarks
    from bodymocap.utils.logging_util import get_session_stats

    lm = get_last_landmarks() or {}
    valid = [n for n, l in lm.items() if l.valid]
    stats = get_session_stats()

    arm = bpy.data.objects.get("HumanoidRig")
    moved = []
    if arm:
        for pb in arm.pose.bones:
            q = pb.rotation_quaternion
            if abs(q.w - 1.0) > 1e-4 or abs(q.x) > 1e-4 or abs(q.y) > 1e-4 or abs(q.z) > 1e-4:
                moved.append(pb.name)

    result = {
        "blender": bpy.app.version_string,
        "camera_active": settings.camera_active,
        "tracking_status": settings.tracking_status,
        "session_stats": stats,
        "last_landmark_count": len(lm),
        "valid_landmarks": len(valid),
        "valid_names": sorted(valid),
        "bones_moved": moved,
        "preview_image": "BodyMocap_Preview" in bpy.data.images,
    }
    print("[LIVE] result:", json.dumps(result))

    out = ROOT / "tests" / "_live_test_result.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # stop capture cleanly via the operator path
    if settings.camera_active:
        settings.camera_active = False
    bpy.ops.wm.quit_blender()


def main():
    scene = bpy.context.scene
    settings = scene.bodymocap

    # Select the armature for live apply + auto-map it
    arm = bpy.data.objects.get("HumanoidRig")
    if arm:
        bpy.context.view_layer.objects.active = arm
        arm.select_set(True)
        bpy.ops.bodymocap.auto_map()
        print("[LIVE] mapped:", len(settings.mapping_entries), "entries")

    import os
    settings.pose_backend = "MEDIAPIPE"
    settings.camera_device_index = 0
    # Optional: point at a video file instead of the webcam (BODYMOCAP_TEST_VIDEO)
    settings.camera_video_path = os.environ.get("BODYMOCAP_TEST_VIDEO", "")
    settings.live_apply = True
    settings.min_confidence = 0.5

    res = bpy.ops.bodymocap.camera_start()
    print("[LIVE] camera_start ->", res)

    bpy.app.timers.register(_tick, first_interval=0.5)


try:
    main()
except Exception:
    traceback.print_exc()
    bpy.ops.wm.quit_blender()

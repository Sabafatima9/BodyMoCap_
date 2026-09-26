"""Run with exec(compile(...), {'__file__': path, '__name__': '__main__'}) in Blender.

Checks evaluated directions and angles, not merely the presence of keyframes.
Creates a separate scene and writes _workflow_result.json; does not quit Blender.
"""
import json
import math
from pathlib import Path
import unittest

import bpy
from mathutils import Quaternion, Vector

from bodymocap.core.types import Landmark, Vec3
from bodymocap.mapping.apply_pose import (
    apply_landmarks_to_rotations, apply_rotations_to_armature,
    build_calibration_from_landmarks,
)
from bodymocap.retarget.transfer import transfer_in_blender


def rig(name, names, length=1.0):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    parent = None
    for i, bone_name in enumerate(names):
        bone = data.edit_bones.new(bone_name)
        bone.head = (i * length, 0, 0)
        bone.tail = ((i + 1) * length, 0, 0)
        bone.parent = parent
        bone.use_connect = parent is not None
        parent = bone
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.previous = bpy.context.window.scene
        self.scene = bpy.data.scenes.new('WorkflowRegression')
        bpy.context.window.scene = self.scene

    def tearDown(self):
        objects = list(self.scene.objects)
        bpy.context.window.scene = self.previous
        for obj in objects:
            data = obj.data
            action = obj.animation_data.action if obj.animation_data else None
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.armatures.remove(data)
            if action and action.users == 0:
                bpy.data.actions.remove(action)
        bpy.data.scenes.remove(self.scene)

    def retarget(self, source_names, target_names, mode, expected):
        source = rig('RegressionSource', source_names, 4 / len(source_names))
        target = rig('RegressionTarget', target_names, 4 / len(target_names))
        for pb in source.pose.bones:
            pb.rotation_mode = mode
            for frame, angle in [(1, 0), (10, 20)]:
                if mode == 'XYZ':
                    pb.rotation_euler = (0, 0, math.radians(angle))
                    pb.keyframe_insert('rotation_euler', frame=frame)
                else:
                    pb.rotation_quaternion = Quaternion((0, 0, 1), math.radians(angle))
                    pb.keyframe_insert('rotation_quaternion', frame=frame)
        action = source.animation_data.action
        ok, message = transfer_in_blender(source.name, target.name, action.name,
                                         'RegressionOutput')
        self.assertTrue(ok, message)
        self.scene.frame_set(10)
        bpy.context.view_layer.update()
        angles = [math.degrees(pb.rotation_quaternion.angle) for pb in target.pose.bones]
        self.assertEqual(len(angles), len(expected))
        for actual, want in zip(angles, expected):
            self.assertAlmostEqual(actual, want, delta=0.05)

    def test_four_bones_to_two(self):
        self.retarget(['Shoulder.L', 'UpperArm.L', 'Forearm.L', 'Hand.L'],
                      ['Arm.L', 'LowerArm.L'], 'QUATERNION', [40, 40])

    def test_two_bones_to_four(self):
        self.retarget(['Arm.L', 'LowerArm.L'],
                      ['Shoulder.L', 'UpperArm.L', 'Forearm.L', 'Hand.L'],
                      'QUATERNION', [10, 10, 10, 10])

    def test_euler_animation_is_transferred(self):
        self.retarget(['Arm.L', 'LowerArm.L'], ['UpperArm.L', 'Forearm.L'],
                      'XYZ', [20, 20])

    def test_mixamo_names_are_transferred(self):
        self.retarget(['mixamorig:LeftArm', 'mixamorig:LeftForeArm'],
                      ['UpperArm.L', 'Forearm.L'], 'QUATERNION', [20, 20])

    def check_camera_pose(self, calibrated, object_scale=(1, 1, 1)):
        arm = rig('CameraRegression', ['UpperArm.L', 'Forearm.L'])
        arm.scale = object_scale
        arm.rotation_euler = (0.2, 0.1, 0.3) if object_scale != (1, 1, 1) else (0, 0, 0)
        bpy.context.view_layer.update()
        mapping = {'upper_arm_L': 'UpperArm.L', 'forearm_L': 'Forearm.L'}
        def landmarks(elbow, wrist):
            return {name: Landmark(name, Vec3(*pos), 1.0, True) for name, pos in [
                ('left_shoulder', (0, 0, 0)), ('left_elbow', elbow), ('left_wrist', wrist)]}
        cal = build_calibration_from_landmarks(landmarks((1, 0, 0), (2, 0, 0))) if calibrated else None
        current = landmarks((0, 1, 0), (1, 1, 0))
        rotations = apply_landmarks_to_rotations(current, mapping, cal, armature_obj=arm)
        apply_rotations_to_armature(arm, rotations)
        bpy.context.view_layer.update()
        for name, direction in [('UpperArm.L', (0, 0, 1)), ('Forearm.L', (1, 0, 0))]:
            pb = arm.pose.bones[name]
            actual = (arm.matrix_world.to_3x3() @ (pb.tail - pb.head)).normalized()
            self.assertGreater(actual.dot(Vector(direction)), 0.999,
                               f'{name}: expected {direction}, got {tuple(actual)}')

    def test_camera_coordinates_and_parent_compensation(self):
        self.check_camera_pose(False)

    def test_calibrated_camera_coordinates_and_parent_compensation(self):
        self.check_camera_pose(True)

    def test_camera_mirrored_rotated_object(self):
        self.check_camera_pose(False, (-1, 1, 1))

    def test_camera_nonuniform_scaled_rotated_object(self):
        self.check_camera_pose(False, (2, 1, 0.5))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests': result.testsRun, 'passed': result.wasSuccessful(),
              'failures': [(str(t), detail) for t, detail in result.failures + result.errors]}
    Path(__file__).with_name('_workflow_result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    main()

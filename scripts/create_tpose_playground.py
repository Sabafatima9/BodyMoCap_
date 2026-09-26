"""Create a fresh, skinned T-pose test scene without replacing existing scenes.

Run in Blender's Python context. The source rig is selected and camera mapping
is prepared; capture stays stopped. No animation is attached to either rig.
"""
import math
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = 0.5
    return mat


def bone_specs(coarse=False):
    bones = [('Hips', (0, 0, .96), (0, 0, 1.08), None)]
    if coarse:
        bones += [('Spine', (0, 0, 1.08), (0, 0, 1.47), 'Hips'),
                  ('Head', (0, 0, 1.47), (0, 0, 1.83), 'Spine')]
        chest = 'Spine'
    else:
        bones += [('Spine', (0, 0, 1.08), (0, 0, 1.28), 'Hips'),
                  ('Chest', (0, 0, 1.28), (0, 0, 1.47), 'Spine'),
                  ('Neck', (0, 0, 1.47), (0, 0, 1.58), 'Chest'),
                  ('Head', (0, 0, 1.58), (0, 0, 1.83), 'Neck')]
        chest = 'Chest'
    for side, sign in [('L', 1), ('R', -1)]:
        def point(x, z):
            return (sign * x, 0, z)
        if coarse:
            bones += [(f'Arm.{side}', point(.19, 1.47), point(.46, 1.47), chest),
                      (f'LowerArm.{side}', point(.46, 1.47), point(.84, 1.47), f'Arm.{side}')]
        else:
            bones += [(f'Shoulder.{side}', point(.04, 1.47), point(.19, 1.47), chest),
                      (f'UpperArm.{side}', point(.19, 1.47), point(.46, 1.47), f'Shoulder.{side}'),
                      (f'Forearm.{side}', point(.46, 1.47), point(.71, 1.47), f'UpperArm.{side}'),
                      (f'Hand.{side}', point(.71, 1.47), point(.84, 1.47), f'Forearm.{side}')]
        bones += [(f'Thigh.{side}', point(.11, .96), point(.11, .54), 'Hips'),
                  (f'Shin.{side}', point(.11, .54), point(.11, .12), f'Thigh.{side}'),
                  (f'Foot.{side}', point(.11, .12), (sign * .11, -.20, .055), f'Shin.{side}')]
    return bones


def make_character(scene, name, x, coarse, body_material):
    data = bpy.data.armatures.new(name + '_Skeleton')
    arm = bpy.data.objects.new(name, data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    specs = bone_specs(coarse)
    for bone_name, head, tail, parent in specs:
        bone = data.edit_bones.new(bone_name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.location.x = x
    arm.show_in_front = True
    arm.data.display_type = 'OCTAHEDRAL'
    for bone in arm.pose.bones:
        bone.rotation_mode = 'QUATERNION'

    vertices, faces, weights = [], [], {}

    def tube(bone_name, start, end, radius_start, radius_end=None):
        start, end = Vector(start), Vector(end)
        radius_end = radius_start if radius_end is None else radius_end
        rotation = (end - start).to_track_quat('Z', 'Y')
        offset = len(vertices)
        sides = 12
        for center, radius in [(start, radius_start), (end, radius_end)]:
            rx, ry = (radius, radius) if isinstance(radius, (float, int)) else radius
            for i in range(sides):
                angle = 2 * math.pi * i / sides
                vertices.append(tuple(center + rotation @ Vector((rx * math.cos(angle), ry * math.sin(angle), 0))))
        faces.append(tuple(offset + i for i in reversed(range(sides))))
        faces.append(tuple(offset + sides + i for i in range(sides)))
        for i in range(sides):
            j = (i + 1) % sides
            faces.append((offset + i, offset + j, offset + sides + j, offset + sides + i))
        weights.setdefault(bone_name, []).extend(range(offset, len(vertices)))

    def sphere(bone_name, center, scale):
        center = Vector(center)
        offset = len(vertices)
        rings, sides = 10, 16
        for j in range(rings + 1):
            theta = math.pi * j / rings
            for i in range(sides):
                phi = 2 * math.pi * i / sides
                vertices.append(tuple(center + Vector((scale[0] * math.sin(theta) * math.cos(phi),
                    scale[1] * math.sin(theta) * math.sin(phi), scale[2] * math.cos(theta)))))
        for j in range(rings):
            for i in range(sides):
                k = (i + 1) % sides
                faces.append((offset+j*sides+i, offset+j*sides+k,
                              offset+(j+1)*sides+k, offset+(j+1)*sides+i))
        weights.setdefault(bone_name, []).extend(range(offset, len(vertices)))

    tube('Hips', (0, 0, .93), (0, 0, 1.075), (.16, .10), (.15, .095))
    tube('Spine', (0, 0, 1.09), (0, 0, 1.27 if not coarse else 1.44),
         (.15, .095), (.18, .105) if not coarse else (.22, .11))
    if not coarse:
        tube('Chest', (0, 0, 1.285), (0, 0, 1.44), (.18, .105), (.22, .11))
    tube('Head' if coarse else 'Neck', (0, 0, 1.48), (0, 0, 1.59), .048)
    sphere('Head', (0, 0, 1.71), (.105, .09, .14))
    for side, sign in [('L', 1), ('R', -1)]:
        upper = f'Arm.{side}' if coarse else f'UpperArm.{side}'
        lower = f'LowerArm.{side}' if coarse else f'Forearm.{side}'
        hand = lower if coarse else f'Hand.{side}'
        tube(upper, (sign*.20, 0, 1.47), (sign*.445, 0, 1.47), .065, .048)
        sphere(upper, (sign*.19, 0, 1.47), (.068, .068, .068))
        sphere(lower, (sign*.46, 0, 1.47), (.049, .049, .049))
        tube(lower, (sign*.475, 0, 1.47), (sign*.70, 0, 1.47), .049, .034)
        sphere(hand, (sign*.775, 0, 1.47), (.075, .035, .05))
        tube(f'Thigh.{side}', (sign*.11, 0, .93), (sign*.11, 0, .56), .078, .055)
        sphere(f'Shin.{side}', (sign*.11, 0, .54), (.054, .054, .054))
        tube(f'Shin.{side}', (sign*.11, 0, .52), (sign*.11, 0, .14), .055, .037)
        sphere(f'Foot.{side}', (sign*.11, -.065, .07), (.06, .14, .065))

    mesh = bpy.data.meshes.new(name + '_BodyMesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name + '_Body', mesh)
    scene.collection.objects.link(obj)
    obj.parent = arm
    obj.data.materials.append(body_material)
    for bone_name, indices in weights.items():
        group = obj.vertex_groups.new(name=bone_name)
        group.add(indices, 1.0, 'REPLACE')
    modifier = obj.modifiers.new('Skeleton Deformation', 'ARMATURE')
    modifier.object = arm
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    # Make viewport clicks select the skeleton through its visible mesh.
    obj.hide_select = True
    assert len(weights) > 8
    assert all(name in arm.data.bones for name in weights)
    return arm, obj


def main():
    current = getattr(bpy.context.scene, 'bodymocap', None)
    if current and current.camera_active:
        raise RuntimeError('Stop capture before creating the test scene.')
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    scene = bpy.data.scenes.new('Fresh_TPose_Playground')
    bpy.context.window.scene = scene
    scene.render.fps = 30
    scene.frame_start, scene.frame_end = 1, 250
    blue = material('TPose_Source_Teal', (.045, .43, .49))
    orange = material('TPose_Target_Amber', (.82, .36, .065))
    source, source_mesh = make_character(scene, 'Source_TPose', -1.05, False, blue)
    target, target_mesh = make_character(scene, 'Target_TPose', 1.05, True, orange)

    # Verify that real armature deformation moves the visible character.
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    def positions():
        return [v.co.copy() for v in source_mesh.evaluated_get(depsgraph).data.vertices]
    before = positions()
    source.pose.bones['UpperArm.L'].rotation_quaternion = Quaternion((0, 0, 1), .4)
    bpy.context.view_layer.update()
    moved = sum((a-b).length > 1e-5 for a, b in zip(before, positions()))
    assert moved > 20, 'Mesh did not follow its armature'
    source.pose.bones['UpperArm.L'].rotation_quaternion = Quaternion()
    bpy.context.view_layer.update()
    assert max((a-b).length for a,b in zip(before, positions())) < 1e-5

    for obj in scene.objects:
        obj.select_set(False)
    source.select_set(True)
    bpy.context.view_layer.objects.active = source
    settings = scene.bodymocap
    settings.pose_backend = 'MEDIAPIPE'
    settings.camera_device_index = 0
    settings.camera_video_path = ''
    settings.live_apply = True
    settings.source_armature = source.name
    settings.target_armature = target.name
    settings.retarget_action = ''
    settings.retarget_new_action = 'MyTake01_Target'
    settings.action_name = 'MyTake01'
    settings.overwrite_action = False
    bpy.ops.bodymocap.auto_map()
    assert len(settings.mapping_entries) == 19
    assert source.animation_data is None and target.animation_data is None
    assert all(abs(p.rotation_quaternion.w - 1) < 1e-6 for p in source.pose.bones)

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            space.show_region_ui = True
            space.shading.type = 'SOLID'
            space.shading.color_type = 'MATERIAL'
            space.region_3d.view_rotation = Quaternion((.7071068, .7071068, 0, 0))
            space.region_3d.view_perspective = 'ORTHO'
            space.region_3d.view_distance = 5.6
            space.region_3d.view_location = (0, 0, .95)
    notes = bpy.data.texts.new('START_HERE_TPose.txt')
    notes.write('''FRESH T-POSE PLAYGROUND

TEAL: Source_TPose (19 bones) -- selected and mapped for the webcam.
AMBER: Target_TPose (13 bones) -- receive a retargeted Action.
Both begin in a clean T-pose with no animation attached.
Select skeletons by their names in the Outliner (top-right object list).
The body meshes are not selectable, so clicking visible bones selects the rig.

CAMERA: BodyMocap > Capture > Start. Keep Source_TPose selected.
Hold a T-pose, then Calibration > Calibrate Rest Pose.
RECORD: Recording > Rec, move, then Recording > Stop and Capture > Stop.
SAVE: Bake / Apply > Action Name (MyTake01), Bake to Action, Apply Action.
In Dope Sheet > Action Editor, enable Fake User (shield) for each saved Action.
File > Save As saves your rigs and retained Actions together in a .blend file.
Recording data is temporary until baked. Use a different name for every take.
Overwrite Action is disabled in this scene.

RETARGET: Source and Target are already filled in. Set Source Action to your
baked take name, choose a new output name, then click Retarget Action.
''')
    output = ROOT / 'fixtures' / 'fresh_tpose_playground.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print({'saved':str(output), 'source':source.name, 'source_bones':len(source.data.bones),
           'target':target.name, 'target_bones':len(target.data.bones),
           'mapped_roles':len(settings.mapping_entries), 'mesh_vertices_moved_in_check':moved})


if __name__ == '__main__':
    main()

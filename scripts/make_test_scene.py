"""Build a test .blend: humanoid armature + camera + light (run inside Blender).

Usage:
  blender --background --python scripts/make_test_scene.py
"""

import bpy
from mathutils import Vector

OUT = r"C:\Users\4G TRADERS\OneDrive\Desktop\BodyMocap\fixtures\bodymocap_test.blend"

# --- reset to default-ish scene ------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=False)

scene = bpy.context.scene

# --- build humanoid armature ---------------------------------------------------
arm_data = bpy.data.armatures.new("HumanoidRig")
arm_obj = bpy.data.objects.new("HumanoidRig", arm_data)
scene.collection.objects.link(arm_obj)
bpy.context.view_layer.objects.active = arm_obj
arm_obj.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")

# (name, head, tail, parent)
BONES = [
    ("Hips",        (0.0, 0.0, 1.00), (0.0, 0.0, 1.10), None),
    ("Spine",       (0.0, 0.0, 1.10), (0.0, 0.0, 1.25), "Hips"),
    ("Chest",       (0.0, 0.0, 1.25), (0.0, 0.0, 1.45), "Spine"),
    ("Neck",        (0.0, 0.0, 1.45), (0.0, 0.0, 1.55), "Chest"),
    ("Head",        (0.0, 0.0, 1.55), (0.0, 0.0, 1.75), "Neck"),
    ("Shoulder.L",  (0.06, 0.0, 1.45), (0.18, 0.0, 1.45), "Chest"),
    ("UpperArm.L",  (0.18, 0.0, 1.45), (0.42, 0.0, 1.45), "Shoulder.L"),
    ("Forearm.L",   (0.42, 0.0, 1.45), (0.66, 0.0, 1.45), "UpperArm.L"),
    ("Hand.L",      (0.66, 0.0, 1.45), (0.78, 0.0, 1.45), "Forearm.L"),
    ("Shoulder.R",  (-0.06, 0.0, 1.45), (-0.18, 0.0, 1.45), "Chest"),
    ("UpperArm.R",  (-0.18, 0.0, 1.45), (-0.42, 0.0, 1.45), "Shoulder.R"),
    ("Forearm.R",   (-0.42, 0.0, 1.45), (-0.66, 0.0, 1.45), "UpperArm.R"),
    ("Hand.R",      (-0.66, 0.0, 1.45), (-0.78, 0.0, 1.45), "Forearm.R"),
    ("Thigh.L",     (0.10, 0.0, 1.00), (0.10, 0.0, 0.55), "Hips"),
    ("Shin.L",      (0.10, 0.0, 0.55), (0.10, 0.0, 0.12), "Thigh.L"),
    ("Foot.L",      (0.10, 0.0, 0.12), (0.10, -0.15, 0.04), "Shin.L"),
    ("Thigh.R",     (-0.10, 0.0, 1.00), (-0.10, 0.0, 0.55), "Hips"),
    ("Shin.R",      (-0.10, 0.0, 0.55), (-0.10, 0.0, 0.12), "Thigh.R"),
    ("Foot.R",      (-0.10, 0.0, 0.12), (-0.10, -0.15, 0.04), "Shin.R"),
]

edit_bones = {}
for name, head, tail, parent in BONES:
    eb = arm_data.edit_bones.new(name)
    eb.head = Vector(head)
    eb.tail = Vector(tail)
    edit_bones[name] = eb
for name, head, tail, parent in BONES:
    if parent:
        edit_bones[name].parent = edit_bones[parent]

bpy.ops.object.mode_set(mode="OBJECT")

# simple visible proxy meshes parented to key bones (bone parenting)
def add_bone_cube(name, bone_name, loc, scale):
    mesh = bpy.data.meshes.new(name + "Mesh")
    sx, sy, sz = scale
    verts = [(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
    faces = [
        (0, 1, 3, 2), (4, 6, 7, 5), (0, 2, 6, 4),
        (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.parent = arm_obj
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    # place at bone head (in bone-local coords parent space is relative to tail)
    obj.matrix_world = (
        arm_obj.matrix_world
        @ arm_obj.pose.bones[bone_name].matrix
        @ __import__("mathutils").Matrix.Translation(Vector((0, -0.1, 0)))
    )
    return obj

add_bone_cube("TorsoMesh", "Chest", (0, 0, 1.35), (0.18, 0.10, 0.20))
add_bone_cube("HeadMesh", "Head", (0, 0, 1.65), (0.10, 0.10, 0.12))

# ensure camera exists and points at the rig
cam = bpy.data.objects.get("Camera")
if cam is None:
    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (0.0, -4.0, 1.4)
cam.rotation_euler = (1.5708, 0.0, 0.0)

# keep default light + cube off to the side
cube = bpy.data.objects.get("Cube")
if cube:
    cube.location = (1.5, 1.5, 0.5)

arm_obj.select_set(True)
bpy.context.view_layer.objects.active = arm_obj

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT)
print("BONES:", [b.name for b in arm_obj.data.bones])

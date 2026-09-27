"""Transfer animation between armatures via N:M chain remapping (FR-070–076).

Blender-dependent parts are guarded; pure remap helpers work offline.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ..core.math3d import quat_identity, quat_normalize
from ..core.types import ChainDefinition, Quat
from .chains import detect_chains, pair_chains
from .proportional import remap_chain


def remap_pose_dict(
    source_rotations: Dict[str, Quat],
    source_chains: Dict[str, ChainDefinition],
    target_chains: Dict[str, ChainDefinition],
    source_lengths: Optional[Dict[str, List[float]]] = None,
    target_lengths: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Quat]:
    """Remap one frame of bone rotations from source chains to target chains."""
    source_lengths = source_lengths or {}
    target_lengths = target_lengths or {}
    result: Dict[str, Quat] = {}
    pairs = pair_chains(source_chains, target_chains)
    for src_chain, tgt_chain in pairs:
        src_bones = src_chain.bone_names
        tgt_bones = tgt_chain.bone_names
        deltas = [
            quat_normalize(source_rotations.get(b, quat_identity()))
            for b in src_bones
        ]
        s_len = source_lengths.get(src_chain.name) or [1.0] * len(src_bones)
        t_len = target_lengths.get(tgt_chain.name) or [1.0] * len(tgt_bones)
        # pad/truncate lengths
        if len(s_len) != len(src_bones):
            s_len = [1.0] * len(src_bones)
        if len(t_len) != len(tgt_bones):
            t_len = [1.0] * len(tgt_bones)
        remapped = remap_chain(deltas, s_len, t_len)
        for bone, q in zip(tgt_bones, remapped):
            result[bone] = q
    return result


def transfer_action_frames(
    frames: List[Dict[str, Quat]],
    source_bone_names: Sequence[str],
    target_bone_names: Sequence[str],
    source_lengths: Optional[Dict[str, List[float]]] = None,
    target_lengths: Optional[Dict[str, List[float]]] = None,
) -> List[Dict[str, Quat]]:
    """Batch-remap a list of pose dicts."""
    src_chains = detect_chains(list(source_bone_names))
    tgt_chains = detect_chains(list(target_bone_names))
    out = []
    for fr in frames:
        out.append(
            remap_pose_dict(fr, src_chains, tgt_chains, source_lengths, target_lengths)
        )
    return out


def transfer_in_blender(
    source_armature_name: str,
    target_armature_name: str,
    action_name: str,
    new_action_name: str,
    start_frame: int = 1,
) -> Tuple[bool, str]:
    """Blender-side transfer: source Action → new Action on target (FR-076)."""
    try:
        import bpy
        from mathutils import Quaternion
    except ImportError:
        return False, "bpy not available"

    src = bpy.data.objects.get(source_armature_name)
    tgt = bpy.data.objects.get(target_armature_name)
    if src is None or src.type != "ARMATURE":
        return False, f"Source armature not found: {source_armature_name}"
    if tgt is None or tgt.type != "ARMATURE":
        return False, f"Target armature not found: {target_armature_name}"

    action = bpy.data.actions.get(action_name)
    if action is None:
        if src.animation_data and src.animation_data.action:
            action = src.animation_data.action
        else:
            return False, f"Action not found: {action_name}"

    src_bones = [b.name for b in src.data.bones]
    tgt_bones = [b.name for b in tgt.data.bones]
    src_chains = detect_chains(src_bones)
    tgt_chains = detect_chains(tgt_bones)
    pairs = pair_chains(src_chains, tgt_chains)
    if not pairs:
        return False, (
            f"No matching bone chains between '{source_armature_name}' "
            f"({', '.join(src_chains) or 'none detected'}) and '{target_armature_name}' "
            f"({', '.join(tgt_chains) or 'none detected'}). Bones need recognisable names "
            "such as UpperArm.L / Forearm.L, Thigh.R / Shin.R, Hips / Spine."
        )

    # Rest lengths from edit bones (head-tail)
    def bone_lengths(arm_obj, chain: ChainDefinition) -> List[float]:
        lengths = []
        for bn in chain.bone_names:
            bone = arm_obj.data.bones.get(bn)
            if bone:
                lengths.append((bone.tail_local - bone.head_local).length)
            else:
                lengths.append(1.0)
        return lengths

    src_lens = {n: bone_lengths(src, c) for n, c in src_chains.items()}
    tgt_lens = {n: bone_lengths(tgt, c) for n, c in tgt_chains.items()}

    from ..utils.blender_compat import clear_action_fcurves, ensure_action_slot

    # Sample frames from action
    frame_start = int(action.frame_range[0])
    frame_end = int(action.frame_range[1])
    scene = bpy.context.scene

    if new_action_name in bpy.data.actions:
        new_action = bpy.data.actions[new_action_name]
        clear_action_fcurves(new_action)
    else:
        new_action = bpy.data.actions.new(new_action_name)

    if tgt.animation_data is None:
        tgt.animation_data_create()
    prev_action = tgt.animation_data.action
    tgt.animation_data.action = new_action
    ensure_action_slot(tgt.animation_data, new_action, tgt)

    # Ensure pose mode rotations are quaternion
    for pb in tgt.pose.bones:
        pb.rotation_mode = "QUATERNION"

    # Temporarily evaluate source
    if src.animation_data is None:
        src.animation_data_create()
    src_prev_action = src.animation_data.action
    src.animation_data.action = action
    ensure_action_slot(src.animation_data, action, src)

    prev_frame = scene.frame_current
    keyed_bones = set()
    # Root translation (first spine-chain bone, e.g. Hips) is carried over in world
    # space, scaled by the ratio of hip heights so a bigger rig takes bigger steps.
    src_root = src_chains["spine"].bone_names[0] if "spine" in src_chains else None
    tgt_root = tgt_chains["spine"].bone_names[0] if "spine" in tgt_chains else None
    root_scale = 1.0
    if src_root and tgt_root:
        src_h = (src.matrix_world @ src.data.bones[src_root].head_local).z
        tgt_h = (tgt.matrix_world @ tgt.data.bones[tgt_root].head_local).z
        root_scale = (tgt_h / src_h) if abs(src_h) > 1e-6 and abs(tgt_h) > 1e-6 else 1.0
        src_root_to_world = src.matrix_world.to_3x3() @ src.data.bones[src_root].matrix_local.to_3x3()
        world_to_tgt_root = (
            tgt.matrix_world.to_3x3() @ tgt.data.bones[tgt_root].matrix_local.to_3x3()
        ).inverted_safe()

    for f in range(frame_start, frame_end + 1):
        scene.frame_set(f)
        src_rots: Dict[str, Quat] = {}
        for pb in src.pose.bones:
            # Imported actions commonly animate Euler or axis-angle channels.
            # matrix_basis reflects the bone's active rotation representation.
            q = pb.matrix_basis.to_quaternion()
            src_rots[pb.name] = Quat(q.w, q.x, q.y, q.z)
        remapped = remap_pose_dict(src_rots, src_chains, tgt_chains, src_lens, tgt_lens)
        out_frame = start_frame + (f - frame_start)
        for bone_name, q in remapped.items():
            pb = tgt.pose.bones.get(bone_name)
            if pb is None:
                continue
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = Quaternion((q.w, q.x, q.y, q.z))
            pb.keyframe_insert(data_path="rotation_quaternion", frame=out_frame)
            keyed_bones.add(bone_name)
        if src_root and tgt_root:
            src_pb = src.pose.bones[src_root]
            tgt_pb = tgt.pose.bones[tgt_root]
            if src_pb.location.length > 1e-9 or tgt_pb.location.length > 1e-9:
                world_offset = src_root_to_world @ src_pb.location
                tgt_pb.location = (world_to_tgt_root @ world_offset) * root_scale
                tgt_pb.keyframe_insert(data_path="location", frame=out_frame)

    scene.frame_set(prev_frame)
    if src_prev_action is not None:
        src.animation_data.action = src_prev_action
    tgt.animation_data.action = new_action
    ensure_action_slot(tgt.animation_data, new_action, tgt)
    n_frames = frame_end - frame_start + 1
    chain_desc = ", ".join(f"{s.name} {len(s.bone_names)}->{len(t.bone_names)}" for s, t in pairs)
    return True, (
        f"Retargeted {n_frames} frames onto {len(keyed_bones)} bones of {target_armature_name} "
        f"-> Action '{new_action.name}' ({chain_desc})"
    )

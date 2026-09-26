"""Proportional N:M chain remapping — aggregation and splitting (FR-072–074).

Pure Python, no bpy.

N→M (N > M): partition source chain into M contiguous groups by rest-length
parameterization; aggregate each group's delta rotations via quaternion average /
cumulative swing product.

M←N (N < M, i.e. split): distribute source orientations across target bones by
interpolating along the chain parameter.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from ..core.math3d import (
    clamp,
    cumulative_quat_product,
    normalize_weights,
    quat_average,
    quat_identity,
    quat_mul,
    quat_normalize,
    quat_slerp,
)
from ..core.types import Quat


def chain_parameter_breaks(rest_lengths: Sequence[float]) -> List[float]:
    """Cumulative normalized parameters [0..1] at each joint after root.

    Returns list of length len(rest_lengths)+1 starting at 0 ending at 1.
    """
    if not rest_lengths:
        return [0.0, 1.0]
    weights = normalize_weights(rest_lengths)
    breaks = [0.0]
    acc = 0.0
    for w in weights:
        acc += w
        breaks.append(acc)
    breaks[-1] = 1.0
    return breaks


def assign_source_intervals_to_targets(
    source_lengths: Sequence[float],
    target_lengths: Sequence[float],
) -> List[Tuple[int, int]]:
    """Return list of (start_src_idx, end_src_idx_exclusive) per target bone.

    Source segments are indexed 0..N-1. Target gets M groups covering all segments.
    Uses proportional rest-length parameterization (FR-072.1 / FR-073).
    """
    n = len(source_lengths)
    m = len(target_lengths)
    if n == 0 or m == 0:
        return []
    if n == m:
        return [(i, i + 1) for i in range(n)]

    src_breaks = chain_parameter_breaks(source_lengths)
    tgt_breaks = chain_parameter_breaks(target_lengths)

    # Mid-parameter of each source segment
    src_mids = [
        0.5 * (src_breaks[i] + src_breaks[i + 1]) for i in range(n)
    ]

    groups: List[List[int]] = [[] for _ in range(m)]
    for si, mid in enumerate(src_mids):
        # Find target interval containing mid
        assigned = m - 1
        for ti in range(m):
            lo = tgt_breaks[ti]
            hi = tgt_breaks[ti + 1]
            if lo <= mid <= hi or (ti == m - 1 and mid >= lo):
                assigned = ti
                break
        groups[assigned].append(si)

    # Ensure contiguous non-empty groups by filling empties from neighbors
    for ti in range(m):
        if not groups[ti]:
            # steal from nearest non-empty
            for d in range(1, m):
                if ti - d >= 0 and groups[ti - d]:
                    groups[ti].append(groups[ti - d].pop())
                    break
                if ti + d < m and groups[ti + d]:
                    groups[ti].append(groups[ti + d].pop(0))
                    break

    # Flatten to contiguous ranges (sort indices)
    result: List[Tuple[int, int]] = []
    used = set()
    cursor = 0
    for ti in range(m):
        idxs = sorted(set(groups[ti]) - used)
        if not idxs:
            # take next unused segment
            while cursor < n and cursor in used:
                cursor += 1
            if cursor < n:
                idxs = [cursor]
        for i in idxs:
            used.add(i)
        start = min(idxs)
        end = max(idxs) + 1
        # expand to include any gap segments not yet used that fall in range
        result.append((start, end))
        cursor = end

    # Fix overlaps / gaps for a clean partition
    clean: List[Tuple[int, int]] = []
    for ti in range(m):
        if ti == 0:
            start = 0
        else:
            start = clean[ti - 1][1]
        if ti == m - 1:
            end = n
        else:
            # proportional cut
            cut_param = tgt_breaks[ti + 1]
            end = n
            for si in range(start, n):
                if src_breaks[si + 1] >= cut_param - 1e-9:
                    end = max(start + 1, si + 1)
                    break
            # leave enough for remaining targets
            remaining_targets = m - ti - 1
            end = min(end, n - remaining_targets)
            end = max(end, start + 1)
        clean.append((start, end))
    return clean


def aggregate_rotations(
    source_deltas: Sequence[Quat],
    source_lengths: Sequence[float],
    target_lengths: Sequence[float],
    mode: str = "cumulative",
) -> List[Quat]:
    """N→M aggregation of bone delta rotations (FR-072.1, FR-073).

    source_deltas: length N (one per source bone)
    Returns M quaternions for target bones.
    """
    n = len(source_deltas)
    m = len(target_lengths)
    if n == 0 or m == 0:
        return [quat_identity() for _ in range(m)]
    if len(source_lengths) != n:
        source_lengths = [1.0] * n
    if len(target_lengths) != m:
        target_lengths = [1.0] * m

    intervals = assign_source_intervals_to_targets(source_lengths, target_lengths)
    out: List[Quat] = []
    for start, end in intervals:
        group = list(source_deltas[start:end])
        if not group:
            out.append(quat_identity())
            continue
        if mode == "average":
            out.append(quat_average(group))
        else:
            # cumulative swing product — preserves total chain twist better
            out.append(quat_normalize(cumulative_quat_product(group)))
    return out


def split_rotations(
    source_deltas: Sequence[Quat],
    source_lengths: Sequence[float],
    target_lengths: Sequence[float],
) -> List[Quat]:
    """N→M splitting when N < M (FR-072.2, FR-074): interpolate along chain.

    Evaluates orientation along the source chain parameter and assigns to each
    target bone the relative rotation between consecutive samples.
    """
    n = len(source_deltas)
    m = len(target_lengths)
    if m == 0:
        return []
    if n == 0:
        return [quat_identity() for _ in range(m)]
    if len(source_lengths) != n:
        source_lengths = [1.0] * n
    if len(target_lengths) != m:
        target_lengths = [1.0] * m
    if n == m:
        return [quat_normalize(q) for q in source_deltas]

    # Build cumulative orientation along source: G[0]=I, G[k]=d0*...*d{k-1}
    G: List[Quat] = [quat_identity()]
    for q in source_deltas:
        G.append(quat_mul(G[-1], quat_normalize(q)))

    src_breaks = chain_parameter_breaks(source_lengths)
    tgt_breaks = chain_parameter_breaks(target_lengths)

    def sample_orientation(u: float) -> Quat:
        u = clamp(u, 0.0, 1.0)
        # Find segment
        for i in range(n):
            lo, hi = src_breaks[i], src_breaks[i + 1]
            if u <= hi or i == n - 1:
                span = hi - lo
                t = 0.0 if span < 1e-12 else (u - lo) / span
                # interpolate global orientation from G[i] to G[i+1]
                return quat_slerp(G[i], G[i + 1], clamp(t, 0.0, 1.0))
        return G[-1]

    # Sample global orientation at each target joint parameter, derive local deltas
    out: List[Quat] = []
    prev_g = sample_orientation(0.0)
    for ti in range(m):
        u = tgt_breaks[ti + 1]
        g = sample_orientation(u)
        # local = prev^{-1} * g
        from ..core.math3d import quat_conjugate

        local = quat_mul(quat_conjugate(prev_g), g)
        out.append(quat_normalize(local))
        prev_g = g
    return out


def remap_chain(
    source_deltas: Sequence[Quat],
    source_lengths: Sequence[float],
    target_lengths: Sequence[float],
) -> List[Quat]:
    """Dispatch aggregate or split based on N vs M."""
    n = len(source_deltas)
    m = len(target_lengths)
    if n == m:
        return [quat_normalize(q) for q in source_deltas]
    if n > m:
        return aggregate_rotations(source_deltas, source_lengths, target_lengths)
    return split_rotations(source_deltas, source_lengths, target_lengths)


# --- Worked examples for documentation / tests ---

def example_arm_4_to_2(
    source_deltas: Sequence[Quat],
    source_lengths: Sequence[float] = (1.0, 1.0, 1.0, 1.0),
    target_lengths: Sequence[float] = (2.0, 2.0),
) -> List[Quat]:
    """FR-073: 4→2 arm — proximal two → upper_arm, distal two → forearm."""
    assert len(source_deltas) == 4
    return aggregate_rotations(source_deltas, source_lengths, target_lengths)


def example_arm_2_to_4(
    source_deltas: Sequence[Quat],
    source_lengths: Sequence[float] = (2.0, 2.0),
    target_lengths: Sequence[float] = (1.0, 1.0, 1.0, 1.0),
) -> List[Quat]:
    """FR-074: 2→4 arm via proportional splitting."""
    assert len(source_deltas) == 2
    return split_rotations(source_deltas, source_lengths, target_lengths)

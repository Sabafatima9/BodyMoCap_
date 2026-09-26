"""Recording session storage (FR-050–053). Pure Python."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..core.types import Quat, RecordingFrame, TrackingState


@dataclass
class RecordingSession:
    frames: List[RecordingFrame] = field(default_factory=list)
    is_recording: bool = False
    is_paused: bool = False
    fps: float = 24.0
    degraded_warn_fraction: float = 0.15
    name: str = "Take"

    def start(self, fps: float = 24.0) -> None:
        self.frames.clear()
        self.is_recording = True
        self.is_paused = False
        self.fps = fps

    def pause(self) -> None:
        if self.is_recording:
            self.is_paused = True

    def resume(self) -> None:
        if self.is_recording:
            self.is_paused = False

    def stop(self) -> None:
        self.is_recording = False
        self.is_paused = False

    def discard(self) -> None:
        self.frames.clear()
        self.is_recording = False
        self.is_paused = False

    def append(
        self,
        frame_index: int,
        bone_rotations: Dict[str, Quat],
        tracking_state: TrackingState = TrackingState.OK,
        timestamp: Optional[float] = None,
    ) -> None:
        if not self.is_recording or self.is_paused:
            return
        ts = timestamp if timestamp is not None else frame_index / max(self.fps, 1e-6)
        self.frames.append(
            RecordingFrame(
                frame_index=frame_index,
                bone_rotations=dict(bone_rotations),
                tracking_state=tracking_state,
                timestamp=ts,
            )
        )

    def frame_count(self) -> int:
        return len(self.frames)

    def degraded_or_lost_fraction(self) -> float:
        if not self.frames:
            return 0.0
        bad = sum(
            1
            for f in self.frames
            if f.tracking_state in (TrackingState.DEGRADED, TrackingState.LOST)
        )
        return bad / len(self.frames)

    def should_warn_tracking(self) -> bool:
        return self.degraded_or_lost_fraction() > self.degraded_warn_fraction

    def tracking_warning_message(self) -> str:
        frac = self.degraded_or_lost_fraction()
        pct = int(round(frac * 100))
        return (
            f"Tracking was Degraded/Lost for {pct}% of frames "
            f"(threshold {int(self.degraded_warn_fraction * 100)}%)."
        )

    def to_serializable(self) -> dict:
        return {
            "name": self.name,
            "fps": self.fps,
            "frames": [
                {
                    "frame_index": f.frame_index,
                    "timestamp": f.timestamp,
                    "tracking_state": f.tracking_state.name,
                    "bone_rotations": {
                        k: list(v.as_tuple()) for k, v in f.bone_rotations.items()
                    },
                }
                for f in self.frames
            ],
        }


# Module-level singleton used by operators when bpy props hold a handle
_ACTIVE_SESSION: Optional[RecordingSession] = None


def get_active_session() -> RecordingSession:
    global _ACTIVE_SESSION
    if _ACTIVE_SESSION is None:
        _ACTIVE_SESSION = RecordingSession()
    return _ACTIVE_SESSION


def reset_active_session() -> RecordingSession:
    global _ACTIVE_SESSION
    _ACTIVE_SESSION = RecordingSession()
    return _ACTIVE_SESSION

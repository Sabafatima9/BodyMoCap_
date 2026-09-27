"""Recording session storage (FR-050–053). Pure Python.

Frames are indexed by *elapsed wall-clock time × scene FPS* (FR-051), not by the
number of capture ticks, so a take plays back at the speed it was performed even
when pose inference runs slower or faster than the scene frame rate. Pauses are
subtracted from the elapsed time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..core.types import Quat, RecordingFrame, TrackingState, Vec3


@dataclass
class RecordingSession:
    frames: List[RecordingFrame] = field(default_factory=list)
    is_recording: bool = False
    is_paused: bool = False
    fps: float = 24.0
    degraded_warn_fraction: float = 0.15
    name: str = "Take"
    start_time: Optional[float] = None
    paused_total: float = 0.0
    _pause_started: Optional[float] = None

    def start(self, fps: float = 24.0, timestamp: Optional[float] = None) -> None:
        self.frames.clear()
        self.is_recording = True
        self.is_paused = False
        self.fps = fps
        self.start_time = timestamp if timestamp is not None else time.time()
        self.paused_total = 0.0
        self._pause_started = None

    def pause(self, timestamp: Optional[float] = None) -> None:
        if self.is_recording and not self.is_paused:
            self.is_paused = True
            self._pause_started = timestamp if timestamp is not None else time.time()

    def resume(self, timestamp: Optional[float] = None) -> None:
        if self.is_recording and self.is_paused:
            now = timestamp if timestamp is not None else time.time()
            if self._pause_started is not None:
                self.paused_total += max(0.0, now - self._pause_started)
            self._pause_started = None
            self.is_paused = False

    def stop(self) -> None:
        if self.is_paused:
            self.resume()
        self.is_recording = False
        self.is_paused = False

    def discard(self) -> None:
        self.frames.clear()
        self.is_recording = False
        self.is_paused = False
        self.start_time = None

    def frame_index_for(self, timestamp: float) -> int:
        """Scene-frame offset (from take start) for a wall-clock timestamp."""
        if self.start_time is None:
            return len(self.frames)
        elapsed = max(0.0, timestamp - self.start_time - self.paused_total)
        return int(round(elapsed * max(self.fps, 1e-6)))

    def append(
        self,
        frame_index: Optional[int] = None,
        bone_rotations: Optional[Dict[str, Quat]] = None,
        tracking_state: TrackingState = TrackingState.OK,
        timestamp: Optional[float] = None,
        bone_locations: Optional[Dict[str, Vec3]] = None,
    ) -> Optional[RecordingFrame]:
        """Store one sample. Returns the stored frame or None when not recording.

        ``frame_index`` may be given explicitly (offline tests); otherwise it is
        derived from ``timestamp``. Several samples landing on the same scene
        frame replace each other so the take never contains duplicate frames.
        """
        if not self.is_recording or self.is_paused:
            return None
        ts = timestamp if timestamp is not None else time.time()
        if frame_index is None:
            frame_index = self.frame_index_for(ts)
        frame = RecordingFrame(
            frame_index=frame_index,
            bone_rotations=dict(bone_rotations or {}),
            tracking_state=tracking_state,
            timestamp=ts,
            bone_locations=dict(bone_locations or {}),
        )
        if self.frames and self.frames[-1].frame_index == frame_index:
            self.frames[-1] = frame
        else:
            self.frames.append(frame)
        return frame

    def frame_count(self) -> int:
        return len(self.frames)

    def last_frame_index(self) -> int:
        return self.frames[-1].frame_index if self.frames else -1

    def duration_seconds(self) -> float:
        if not self.frames:
            return 0.0
        return (self.frames[-1].frame_index - self.frames[0].frame_index + 1) / max(self.fps, 1e-6)

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
                    "bone_locations": {
                        k: list(v.as_tuple()) for k, v in f.bone_locations.items()
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

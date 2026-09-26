"""Session diagnostics logging (FR-081)."""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

_LOGGER: Optional[logging.Logger] = None
_SESSION_STATS: Dict[str, Any] = {}


def get_logger(name: str = "bodymocap") -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("[BodyMocap] %(levelname)s: %(message)s")
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        _LOGGER = logger
    return _LOGGER


def log_info(msg: str) -> None:
    get_logger().info(msg)


def log_warning(msg: str) -> None:
    get_logger().warning(msg)


def log_error(msg: str) -> None:
    get_logger().error(msg)


def reset_session_stats() -> None:
    global _SESSION_STATS
    _SESSION_STATS = {
        "device_index": None,
        "backend": None,
        "frame_count": 0,
        "low_confidence_frames": 0,
        "fps_samples": [],
    }


def update_session_stats(**kwargs: Any) -> None:
    _SESSION_STATS.update({k: v for k, v in kwargs.items() if v is not None})
    if "fps" in kwargs and kwargs["fps"] is not None:
        samples = _SESSION_STATS.setdefault("fps_samples", [])
        samples.append(float(kwargs["fps"]))
        if len(samples) > 300:
            del samples[: len(samples) - 300]


def record_frame(low_confidence: bool = False) -> None:
    _SESSION_STATS["frame_count"] = int(_SESSION_STATS.get("frame_count", 0)) + 1
    if low_confidence:
        _SESSION_STATS["low_confidence_frames"] = (
            int(_SESSION_STATS.get("low_confidence_frames", 0)) + 1
        )


def session_summary() -> str:
    fc = int(_SESSION_STATS.get("frame_count", 0))
    low = int(_SESSION_STATS.get("low_confidence_frames", 0))
    pct = (100.0 * low / fc) if fc else 0.0
    samples = _SESSION_STATS.get("fps_samples") or []
    avg_fps = sum(samples) / len(samples) if samples else 0.0
    return (
        f"device={_SESSION_STATS.get('device_index')} "
        f"backend={_SESSION_STATS.get('backend')} "
        f"frames={fc} low_conf={pct:.1f}% avg_fps={avg_fps:.1f}"
    )


def get_session_stats() -> Dict[str, Any]:
    return dict(_SESSION_STATS)

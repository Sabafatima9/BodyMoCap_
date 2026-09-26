"""Abstract pose estimation backend (FR-020)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..core.types import PoseFrame


class PoseBackend(ABC):
    """Interface: infer(frame) → PoseFrame with named landmarks + confidence."""

    name: str = "abstract"

    @abstractmethod
    def initialize(self, **kwargs: Any) -> bool:
        """Prepare model / resources. Return False on failure."""

    @abstractmethod
    def infer(self, frame_bgr: Any, frame_index: int = 0, timestamp: float = 0.0) -> PoseFrame:
        """Run pose estimation on a BGR numpy array (or compatible)."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release resources."""

    def is_available(self) -> bool:
        return True

    def info(self) -> Dict[str, str]:
        return {"name": self.name, "local": "true"}

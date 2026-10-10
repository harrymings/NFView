"""Models functionality for NFView."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path



class ScanCancelled(Exception):
    """Cooperative cancellation between files; preserve existing cache entries."""

@dataclass(frozen=True)
class ImageScore:
    path: Path
    score: float
    error: str = ""

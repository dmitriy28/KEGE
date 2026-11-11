from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Return an asset path both from source and from a PyInstaller bundle."""

    bundled_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundled_root) if bundled_root else Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


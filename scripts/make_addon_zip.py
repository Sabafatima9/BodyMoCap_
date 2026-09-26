#!/usr/bin/env python3
"""Zip the bodymocap/ package for Blender Preferences → Install."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bodymocap"
DIST = ROOT / "dist"
OUT = DIST / "bodymocap.zip"


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SRC.rglob("*")):
            if path.is_dir():
                continue
            if path.name.endswith(".pyc") or "__pycache__" in path.parts:
                continue
            arc = Path("bodymocap") / path.relative_to(SRC)
            zf.write(path, arcname=str(arc).replace("\\", "/"))
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

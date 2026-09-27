#!/usr/bin/env python3
"""Copy bodymocap/ into Blender's user add-ons folder and hot-reload it via BlenderMCP.

Usage:
  python scripts/dev_reload_addon.py            # Blender 5.2 user add-ons dir
  python scripts/dev_reload_addon.py --version 4.5
  python scripts/dev_reload_addon.py --no-reload # copy only

Requires the BlenderMCP add-on server running on port 9876 for the reload step.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bodymocap"

RELOAD_CODE = r'''
import bpy, sys, importlib
name = "bodymocap"
try:
    if name in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_disable(module=name)
except Exception as exc:
    print("disable failed:", exc)
for mod in [m for m in list(sys.modules) if m == name or m.startswith(name + ".")]:
    del sys.modules[mod]
importlib.invalidate_caches()
bpy.ops.preferences.addon_enable(module=name)
import bodymocap
print("reloaded bodymocap", bodymocap.bl_info["version"], "enabled:", name in bpy.context.preferences.addons)
'''


def addons_dir(version: str) -> Path:
    if os.name == "nt":
        base = Path(os.environ["APPDATA"]) / "Blender Foundation" / "Blender"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Blender"
    else:
        base = Path.home() / ".config" / "blender"
    return base / version / "scripts" / "addons"


def copy_addon(dest_root: Path) -> Path:
    dest = dest_root / "bodymocap"
    dest_root.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="5.2", help="Blender version folder (default 5.2)")
    parser.add_argument("--no-reload", action="store_true")
    parser.add_argument("--port", type=int, default=9876)
    args = parser.parse_args()

    dest = copy_addon(addons_dir(args.version))
    print(f"Copied add-on to {dest}")
    if args.no_reload:
        return 0

    sys.path.insert(0, str(ROOT / "scripts"))
    from blender_mcp_client import execute  # noqa: E402

    try:
        print(execute(RELOAD_CODE, port=args.port), end="")
    except Exception as exc:
        print(f"Reload via BlenderMCP failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

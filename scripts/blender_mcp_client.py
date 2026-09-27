#!/usr/bin/env python3
"""Send Python to a running Blender through the BlenderMCP socket (port 9876).

Usage:
  python scripts/blender_mcp_client.py path/to/script.py      # run a file
  python scripts/blender_mcp_client.py -c "print(bpy.app.version)"
  python scripts/blender_mcp_client.py --screenshot out.png    # viewport grab

The BlenderMCP add-on must be enabled in Blender with its server started.
Captured stdout of the executed code is printed here.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path


def send(command: dict, host: str = "localhost", port: int = 9876, timeout: float = 120.0) -> dict:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(json.dumps(command).encode("utf-8"))
        buffer = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buffer += chunk
            try:
                return json.loads(buffer.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    raise RuntimeError("Connection closed before a full JSON response arrived")


def execute(code: str, **kwargs) -> str:
    response = send({"type": "execute_code", "params": {"code": code}}, **kwargs)
    if response.get("status") != "success":
        raise RuntimeError(response.get("message", str(response)))
    return response.get("result", {}).get("result", "")


def main() -> int:
    # Blender output may contain non-cp1252 characters; never let printing fail.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", nargs="?", help="Python file to execute inside Blender")
    parser.add_argument("-c", "--code", help="Inline Python code to execute inside Blender")
    parser.add_argument("--screenshot", metavar="PATH", help="Save a viewport screenshot to PATH")
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if args.screenshot:
        response = send(
            {
                "type": "get_viewport_screenshot",
                "params": {"filepath": str(Path(args.screenshot).resolve()), "max_size": 1200},
            },
            port=args.port,
            timeout=args.timeout,
        )
        print(json.dumps(response, indent=2))
        return 0 if response.get("status") == "success" else 1

    if args.code:
        code = args.code
    elif args.script:
        code = Path(args.script).read_text(encoding="utf-8")
    else:
        parser.error("Provide a script path, -c CODE, or --screenshot PATH")
        return 2

    try:
        print(execute(code, port=args.port, timeout=args.timeout), end="")
    except (ConnectionRefusedError, socket.timeout) as exc:
        print(f"Cannot reach Blender MCP on port {args.port}: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Blender error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

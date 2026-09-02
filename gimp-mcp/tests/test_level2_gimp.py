#!/usr/bin/env python3
"""Level 2 -- needs a real GIMP 3 install (gimp-console), no GUI.

Boots the real mcp-bridge OPERATIONS inside gimp-console via
gimp_bridge_headless.py, then drives them with server.py's own
GimpBridgeClient. Exercises the GIMP 3 API paths (create image, add
layer, add text layer, selections, PDB call, python.eval, export).

Run:  gimp_mcp_server/.venv/bin/python tests/test_level2_gimp.py
Env:  GIMP_CONSOLE=/path/to/gimp-console-3.2   (auto-detected on macOS)
"""
import os
import shutil
import socket
import struct
import json
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "gimp_mcp_server"))
from server import GimpBridgeClient, BridgeError  # type: ignore[import-not-found] # noqa: E402

HEADLESS = os.path.join(REPO, "tests", "gimp_bridge_headless.py")
OUT = os.path.join(REPO, "tests", ".level2_export.png")

CANDIDATES = [
    os.environ.get("GIMP_CONSOLE", ""),
    shutil.which("gimp-console-3.2") or "",
    shutil.which("gimp-console") or "",
    "/Applications/GIMP.app/Contents/MacOS/gimp-console-3.2",
    "/Applications/GIMP.app/Contents/MacOS/gimp-console",
]
GIMP_CONSOLE = next((c for c in CANDIDATES if c and os.path.exists(c)), None)


def main():
    if not GIMP_CONSOLE:
        print("SKIP: no gimp-console found (set GIMP_CONSOLE=...)")
        sys.exit(77)

    if os.path.exists(OUT):
        os.remove(OUT)

    env = dict(os.environ, GIMP_MCP_BRIDGE_FILE=os.path.join(REPO, "mcp-bridge", "mcp-bridge.py"))
    with open(HEADLESS) as fh:
        script = fh.read()
    # -i = no GUI; data + fonts stay enabled (text layers need fonts)
    gimp = subprocess.Popen(
        [GIMP_CONSOLE, "-i", "--batch-interpreter", "python-fu-eval", "-b", "-", "--quit"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    gimp.stdin.write(script)
    gimp.stdin.close()

    b = GimpBridgeClient()
    results = []

    def check(label, fn):
        try:
            data = fn()
            results.append((True, label))
            print(f"[ok]   {label}: {data}")
            return data
        except Exception as exc:
            results.append((False, label))
            print(f"[FAIL] {label}: {exc!r}")
            return None

    try:
        for _ in range(90):
            try:
                b.call("ping")
                break
            except BridgeError:
                time.sleep(1)
        else:
            print("FAIL: headless bridge never came up")
            sys.exit(1)

        check("ping", lambda: b.call("ping"))
        img = check("image.create 400x300",
                    lambda: b.call("image.create", width=400, height=300, name="lvl2"))
        iid = img["id"] if img else None
        if iid:
            check("image.list", lambda: b.call("image.list"))
            check("image.get", lambda: b.call("image.get", image_id=iid))
            check("layer.add", lambda: b.call("layer.add", image_id=iid, name="extra"))
            check("layer.add_text", lambda: b.call("layer.add_text", image_id=iid,
                  text="hello gimp", x=20, y=20, font="Sans", size=32, color=[255, 0, 0]))
            check("layer.list", lambda: b.call("layer.list", image_id=iid))
            check("image.select_rectangle", lambda: b.call("image.select_rectangle",
                  image_id=iid, x=10, y=10, width=50, height=50))
            check("image.select_none", lambda: b.call("image.select_none", image_id=iid))
            check("pdb.call gimp-version", lambda: b.call("pdb.call",
                  procedure="gimp-version", args=[]))
            check("python.eval", lambda: b.call("python.eval",
                  code="result = [i.get_name() for i in Gimp.get_images()]"))
            check("image.export png", lambda: b.call("image.export", image_id=iid, path=OUT))
            exported_ok = os.path.exists(OUT) and os.path.getsize(OUT) > 0
            results.append((exported_ok, "exported file on disk"))
            print(("[ok]   " if exported_ok else "[FAIL] ")
                  + f"exported file on disk: {OUT}")
            check("image.delete", lambda: b.call("image.delete", image_id=iid))
    finally:
        try:
            s = socket.socket()
            s.settimeout(3)
            s.connect(("127.0.0.1", 9877))
            p = json.dumps({"op": "server.shutdown"}).encode()
            s.sendall(struct.pack("!I", len(p)) + p)
            s.close()
        except Exception:
            pass
        try:
            gimp.wait(timeout=15)
        except subprocess.TimeoutExpired:
            gimp.kill()

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\nLevel 2: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

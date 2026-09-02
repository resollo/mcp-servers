#!/usr/bin/env python3
"""Level 1 -- no GIMP needed.

Starts mock_bridge.py, launches gimp_mcp_server/server.py as a real MCP
stdio server against it, then checks tool discovery and that each tool
call is forwarded to the bridge with the right op name and args.

Run:  gimp_mcp_server/.venv/bin/python tests/test_level1_protocol.py
"""
import asyncio
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(REPO, "gimp_mcp_server", "server.py")
VENV_PY = os.path.join(REPO, "gimp_mcp_server", ".venv", "bin", "python")
MOCK = os.path.join(REPO, "tests", "mock_bridge.py")
LOG = os.path.join(REPO, "tests", ".mock_bridge.log")

from mcp.client import Client  # type: ignore[import-not-found] # noqa: E402
from mcp.client.stdio import StdioServerParameters  # type: ignore[import-not-found] # noqa: E402


def _text(result):
    return "\n".join(getattr(c, "text", str(c)) for c in result.content)


async def run():
    params = StdioServerParameters(command=VENV_PY, args=[SERVER])
    ok = True
    async with Client(params, raise_exceptions=True) as client:
        names = sorted(t.name for t in (await client.list_tools()).tools)
        print(f"discovered {len(names)} tools")
        for want in ("gimp_ping", "gimp_create_image", "gimp_run_script",
                     "gimp_run_pdb_procedure", "gimp_add_text_layer"):
            hit = want in names
            ok &= hit
            print(f"  [{'ok' if hit else 'MISSING'}] {want}")

        print("gimp_ping ->", _text(await client.call_tool("gimp_ping", {})))
        print("gimp_create_image ->", _text(await client.call_tool(
            "gimp_create_image", {"width": 800, "height": 600, "name": "hello"})))
        print("gimp_run_script ->", _text(await client.call_tool(
            "gimp_run_script", {"code": "result = 2 + 2"})))

    print("\n--- bridge received ---")
    seen = [json.loads(x) for x in open(LOG).read().splitlines() if x.strip()]
    for row in seen:
        print(" ", row)
    ops = {r["op"] for r in seen}
    for need in ("ping", "image.create", "python.eval"):
        if need not in ops:
            ok = False
            print(f"  MISSING forwarded op: {need}")
    create = next((r for r in seen if r["op"] == "image.create"), None)
    if not create or create["args"].get("width") != 800 or create["args"].get("name") != "hello":
        ok = False
        print("  image.create args not forwarded correctly:", create)
    return ok


def main():
    if os.path.exists(LOG):
        os.remove(LOG)
    mock = subprocess.Popen([sys.executable, MOCK, "--log", LOG],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(1)
        ok = asyncio.run(run())
    finally:
        mock.terminate()
        try:
            mock.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock.kill()
    print("\nLevel 1:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

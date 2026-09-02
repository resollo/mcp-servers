"""Runs INSIDE gimp-console (python-fu-eval), launched by
test_level2_gimp.py. Loads the real OPERATIONS + BridgeServer from
mcp-bridge/mcp-bridge.py (everything before the plug-in registration
class) and serves the TCP bridge, so the host side can exercise the
actual GIMP 3 API calls headlessly.

gimp-console has no display subsystem, so Gimp.Display.new() /
displays_flush() are shimmed to no-ops; every other call forwards to
the real Gimp.
"""
import os
import sys

BRIDGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp-bridge", "mcp-bridge.py",
)
# fallback: env var, since __file__ can be unreliable under python-fu-eval
BRIDGE = os.environ.get("GIMP_MCP_BRIDGE_FILE", BRIDGE)

src = open(BRIDGE).read()
src = src[:src.index("class MCPBridgePlugin")]  # drop plug-in registration + Gimp.main()
ns = {}
exec(compile(src, BRIDGE, "exec"), ns)

_real_gimp = ns["Gimp"]


class _DisplayShim:
    def __init__(self, real):
        self._real = real

    def new(self, *a, **k):
        return None

    def __getattr__(self, name):
        return getattr(self._real, name)


class _GimpShim:
    def __init__(self, real):
        self._real = real
        self.Display = _DisplayShim(real.Display)

    def displays_flush(self, *a, **k):
        return None

    def __getattr__(self, name):
        return getattr(self._real, name)


ns["Gimp"] = _GimpShim(_real_gimp)

sys.stderr.write("HEADLESS BRIDGE: starting on 127.0.0.1:9877\n")
sys.stderr.flush()
ns["BridgeServer"]().serve_forever()
sys.stderr.write("HEADLESS BRIDGE: stopped\n")

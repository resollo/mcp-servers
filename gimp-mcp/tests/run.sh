#!/usr/bin/env bash
# Runs both test levels for the GIMP MCP server.
#   Level 1 -- server.py MCP layer + JSON/TCP forwarding, against a mock bridge (no GIMP)
#   Level 2 -- real mcp-bridge OPERATIONS inside headless gimp-console (needs GIMP 3)
set -euo pipefail
cd "$(dirname "$0")/.."

PY=gimp_mcp_server/.venv/bin/python
if [ ! -x "$PY" ]; then
  echo ">> creating venv + installing mcp"
  python3 -m venv gimp_mcp_server/.venv
  gimp_mcp_server/.venv/bin/pip install -q -r gimp_mcp_server/requirements.txt
fi

echo "=================== Level 1: protocol (no GIMP) ==================="
"$PY" tests/test_level1_protocol.py

echo
echo "=================== Level 2: headless GIMP ======================="
set +e
"$PY" tests/test_level2_gimp.py
rc=$?
set -e
if [ "$rc" -eq 77 ]; then
  echo "(Level 2 skipped -- no gimp-console found)"
  exit 0
fi
exit "$rc"

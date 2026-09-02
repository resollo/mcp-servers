#!/usr/bin/env python3
"""Fake mcp-bridge for Level 1 tests: same 4-byte-length + JSON wire
protocol as mcp-bridge/mcp-bridge.py, but with no GIMP. Logs every
request to --log and returns canned success data, so server.py's MCP
layer and call-forwarding can be tested in isolation."""
import argparse
import json
import socket
import struct

HEADER = 4


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def recv_msg(sock):
    (length,) = struct.unpack("!I", recv_exact(sock, HEADER))
    return json.loads(recv_exact(sock, length).decode())


def send_msg(sock, obj):
    payload = json.dumps(obj).encode()
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def canned(op, args):
    if op == "ping":
        return {"ok": True, "gimp_version": "MOCK-3.0"}
    if op == "image.create":
        return {"id": 1, "name": args.get("name") or "Untitled",
                "width": args["width"], "height": args["height"],
                "type": "RGB", "layers": [10]}
    if op == "image.list":
        return [{"id": 1, "name": "Untitled", "width": 640, "height": 480,
                 "type": "RGB", "layers": [10]}]
    if op == "python.eval":
        return {"result": "mock-eval-ok", "stdout": ""}
    if op == "pdb.call":
        return {"status": "SUCCESS", "values": []}
    return {"echo_op": op, "echo_args": args}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9877)
    ap.add_argument("--log", default="mock_bridge.log")
    a = ap.parse_args()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((a.host, a.port))
        srv.listen(8)
        print(f"mock bridge on {a.host}:{a.port}", flush=True)
        while True:
            client, _ = srv.accept()
            with client:
                client.settimeout(30)
                try:
                    req = recv_msg(client)
                except Exception:
                    continue
                op = req.get("op")
                args = req.get("args") or {}
                with open(a.log, "a") as fh:
                    fh.write(json.dumps({"op": op, "args": args}) + "\n")
                if op == "server.shutdown":
                    send_msg(client, {"status": "success", "data": {"stopped": True}})
                    return
                try:
                    send_msg(client, {"status": "success", "data": canned(op, args)})
                except Exception as exc:
                    send_msg(client, {"status": "error", "message": str(exc)})


if __name__ == "__main__":
    main()

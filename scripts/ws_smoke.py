#!/usr/bin/env python3
"""WebSocket smoke test for the Gryphon backend.

Connects to ws://127.0.0.1:8899/ws, verifies the CONNECTED hello and any
persisted-event replay, then POSTs a chat message via HTTP and verifies the
live task lifecycle events arrive over the socket in real time.

Usage (with the backend running on port 8899):
    python scripts/ws_smoke.py [--host 127.0.0.1] [--port 8899]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

LIFECYCLE = [
    "MESSAGE_RECEIVED",
    "TASK_STARTED",
    "AGENT_STARTED",
    "AGENT_THINKING",
    "TOOL_CALL_STARTED",
    "TOOL_CALL_COMPLETED",
    "AGENT_RESPONSE",
    "TASK_COMPLETED",
]


def post_chat(host: str, port: int, message: str) -> dict:
    req = urllib.request.Request(
        f"http://{host}:{port}/api/chat",
        data=json.dumps({"message": message}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


async def run(host: str, port: int) -> int:
    import websockets

    uri = f"ws://{host}:{port}/ws"
    print(f"[ws_smoke] connecting to {uri}")
    async with websockets.connect(uri) as ws:
        # 1. CONNECTED hello
        hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert hello.get("type") == "CONNECTED", f"expected CONNECTED hello, got: {hello}"
        print(f"[ws_smoke] hello: {json.dumps(hello)}")

        # 2. Replay of persisted events (may be empty on a fresh DB)
        replayed = 0
        while True:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
                replayed += 1
            except asyncio.TimeoutError:
                break
        print(f"[ws_smoke] replayed persisted events: {replayed}")

        # 3. Fire a chat message from a separate thread (HTTP) while we listen
        loop = asyncio.get_running_loop()
        chat_future = loop.run_in_executor(
            None, post_chat, host, port, "What time is it?"
        )

        seen: list[str] = []
        task_id: str | None = None
        deadline = loop.time() + 20
        while loop.time() < deadline and "TASK_COMPLETED" not in seen:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            except asyncio.TimeoutError:
                break
            etype = msg.get("type")
            if etype in LIFECYCLE or etype == "SESSION_CREATED":
                seen.append(etype)
                if task_id is None and msg.get("task_id"):
                    task_id = msg["task_id"]
                print(f"[ws_smoke] live event: {etype} task={msg.get('task_id')}")

        chat_resp = await chat_future
        print(f"[ws_smoke] chat response: {json.dumps(chat_resp)}")

    missing = [t for t in LIFECYCLE if t not in seen]
    assert chat_resp.get("response"), f"empty chat response: {chat_resp}"
    assert not missing, f"missing live lifecycle events: {missing}"
    print("[ws_smoke] PASS: full lifecycle streamed live over WebSocket")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.host, args.port))
    except Exception as exc:  # noqa: BLE001
        print(f"[ws_smoke] FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

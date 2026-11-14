"""Tiny local MCP server (Preview) used by the five-gate example.

Speaks JSON-RPC 2.0 over stdio with newline delimited messages, which is the
MCP stdio transport. It exposes one tool, ``partner.echo``, that echoes its
``message`` argument back. There is no real side effect and no network use.

It counts every ``tools/call`` it receives and writes the count to stderr when
stdin closes, so the caller can show how many tool calls actually happened.
"""

from __future__ import annotations

import json
import sys

PROTOCOL_VERSION = "2025-06-18"
TOOL = {
    "name": "partner.echo",
    "description": "Echo the message argument back (reference tool, no side effect).",
    "inputSchema": {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    },
}


def _reply(msg_id, result=None, error=None) -> None:
    payload = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> int:
    tool_calls = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")
        if msg_id is None:
            continue  # notification, for example notifications/initialized
        if method == "initialize":
            _reply(
                msg_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "amw-demo-echo", "version": "0.1.0"},
                },
            )
        elif method == "tools/list":
            _reply(msg_id, {"tools": [TOOL]})
        elif method == "tools/call":
            tool_calls += 1
            params = msg.get("params") or {}
            if params.get("name") != TOOL["name"]:
                _reply(msg_id, error={"code": -32602, "message": "unknown tool"})
                continue
            message = (params.get("arguments") or {}).get("message", "")
            _reply(
                msg_id,
                {
                    "content": [{"type": "text", "text": message}],
                    "structuredContent": {"echo": message},
                    "isError": False,
                },
            )
        else:
            _reply(msg_id, error={"code": -32601, "message": "method not found"})
    sys.stderr.write(f"echo_mcp_server: tools/call received {tool_calls}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

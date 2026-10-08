"""Offline tests for the CLI and the example retry logic."""

import json
import os
import subprocess
import sys
import threading

from amw_demo.cli import main as cli_main
from amw_demo.client import AmwClient, extract_receipt_id

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
RECEIPT = os.path.join(FIXTURES, "proof_receipt.json")
KEYS = os.path.join(FIXTURES, "proof_trust_keys.json")


def test_cli_verify_ok():
    assert cli_main(["verify", RECEIPT, "--keys", KEYS]) == 0


def test_cli_verify_with_issuer_ok():
    assert (
        cli_main(
            [
                "verify",
                RECEIPT,
                "--keys",
                KEYS,
                "--issuer",
                "https://api.thisisatest.tech",
            ]
        )
        == 0
    )


def test_cli_verify_bad_signature_is_1(tmp_path):
    bad = os.path.join(str(tmp_path), "receipt.json")
    with open(RECEIPT, encoding="utf-8") as handle:
        data = json.load(handle)
    data["signature"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
    with open(bad, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    assert cli_main(["verify", bad, "--keys", KEYS]) == 1


def test_cli_verify_unknown_kid_is_2(tmp_path):
    bad = os.path.join(str(tmp_path), "receipt.json")
    with open(RECEIPT, encoding="utf-8") as handle:
        data = json.load(handle)
    data["kid"] = "no-such-key"
    with open(bad, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    assert cli_main(["verify", bad, "--keys", KEYS]) == 2


def test_cli_verify_missing_file_is_2():
    assert cli_main(["verify", "nope.json", "--keys", KEYS]) == 2


class FakeAmwServer:
    """A tiny fake AMW that replays the original receipt on same-key retry."""

    def __init__(self):
        self.calls = []
        self.by_key = {}
        self._server = None

    def __enter__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.calls.append((self.path, body))
                if self.path == "/v1/permits":
                    self._send({"permit_id": "permit-test-1"})
                elif self.path.startswith("/mcp/tools/"):
                    key = body["mcp_context"]["idempotency_key"]
                    if key in outer.by_key:
                        self._send(outer.by_key[key])
                    else:
                        receipt_id = f"rcpt-{len(outer.by_key) + 1}"
                        response = {
                            "content": [{"type": "text", "text": "echo"}],
                            "isError": False,
                            "structuredContent": {"echo": body["arguments"]},
                            "receipt": {"receipt_id": receipt_id},
                        }
                        outer.by_key[key] = response
                        self._send(response)
                else:
                    self._send({"detail": "not found"}, status=404)

            def do_GET(self):
                outer.calls.append((self.path, None))
                self._send({"detail": "not found"}, status=404)

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        port = self._server.server_address[1]
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()


def test_same_key_retry_returns_identical_receipt():
    with FakeAmwServer() as server:
        client = AmwClient(base_url=server.base_url, api_key="test-key")
        permit = client.create_permit(
            issuer_wallet_id="w-1",
            subject_wallet_id="w-1",
            max_credits="5",
            expires_at="2026-01-01T00:15:00+00:00",
            allowed_tools=["partner.echo"],
            scopes=["tool:partner.echo:invoke", "billing:charge"],
            idempotency_key="permit-key-1",
        )
        assert permit["permit_id"] == "permit-test-1"
        key = "retry-key-1"
        args = {"message": "hello"}
        first = client.invoke("partner.echo", args, "w-1", "permit-test-1", key)
        second = client.invoke("partner.echo", args, "w-1", "permit-test-1", key)
        first_id = extract_receipt_id(first)
        second_id = extract_receipt_id(second)
        assert first_id == second_id
        invokes = [c for c in server.calls if c[0].startswith("/mcp/tools/")]
        assert len(invokes) == 2
        assert len(server.by_key) == 1


def test_new_key_is_a_new_call():
    with FakeAmwServer() as server:
        client = AmwClient(base_url=server.base_url, api_key="test-key")
        args = {"message": "hello"}
        first = client.invoke("partner.echo", args, "w-1", "p-1", "key-a")
        second = client.invoke("partner.echo", args, "w-1", "p-1", "key-b")
        assert extract_receipt_id(first) != extract_receipt_id(second)


def test_permit_echo_retry_missing_key_exits_2():
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    script = os.path.join(repo_root, "examples", "permit_echo_retry.py")
    env = {k: v for k, v in os.environ.items() if k not in ("AMW_API_KEY",)}
    env.pop("AMW_WALLET_ID", None)
    proc = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 2
    assert "AMW_API_KEY" in proc.stdout


def test_verify_example_offline():
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    script = os.path.join(repo_root, "examples", "verify_published_receipt.py")
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, script, "--offline"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Verified" in proc.stdout


class ScriptServer:
    """Localhost stand-in for AMW used to run the example offline."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self._server = None

    def __enter__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_body(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                return json.loads(raw or b"{}")

            def do_POST(self):
                body = self._read_body()
                outer.calls.append((self.path, body))
                for prefix, (status, payload) in outer.routes.items():
                    if self.path.startswith(prefix):
                        self._send(payload, status=status)
                        return
                self._send({"detail": "not found"}, status=404)

            def do_GET(self):
                outer.calls.append((self.path, None))
                for prefix, (status, payload) in outer.routes.items():
                    if self.path.startswith(prefix):
                        self._send(payload, status=status)
                        return
                self._send({"detail": "not found"}, status=404)

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        port = self._server.server_address[1]
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()


def _run_permit_script(env_extra):
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    script = os.path.join(repo_root, "examples", "permit_echo_retry.py")
    env = dict(os.environ)
    env.pop("AMW_ISSUER_WALLET_ID", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_permit_echo_retry_401_exits_2_without_key_leak():
    sentinel = "sentinel-key-for-401-test"
    routes = {"/": (401, {"detail": "missing credentials"})}
    with ScriptServer(routes) as server:
        proc = _run_permit_script(
            {
                "AMW_API_KEY": sentinel,
                "AMW_WALLET_ID": "w-demo",
                "AMW_BASE_URL": server.base_url,
            }
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 2
    assert "Traceback" not in combined
    assert sentinel not in combined
    assert "Getting a key" in combined


def test_permit_echo_retry_is_error_exits_1_before_retry():
    routes = {
        "/v1/permits": (200, {"permit_id": "permit-test-1"}),
        "/mcp/tools/": (
            200,
            {
                "content": [{"type": "text", "text": "broken"}],
                "isError": True,
                "structuredContent": {"echo": {}},
                "receipt": {
                    "receipt_id": "rcpt-1",
                    "outcome": "error",
                    "reason": "upstream tool failed",
                },
            },
        ),
    }
    with ScriptServer(routes) as server:
        proc = _run_permit_script(
            {
                "AMW_API_KEY": "test-key",
                "AMW_WALLET_ID": "w-demo",
                "AMW_BASE_URL": server.base_url,
            }
        )
        invokes = [c for c in server.calls if c[0].startswith("/mcp/tools/")]
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "Traceback" not in combined
    assert "upstream tool failed" in combined
    assert len(invokes) == 1

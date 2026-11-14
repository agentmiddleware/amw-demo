"""Offline tests for the Preview five-gate example."""

import json
import os
import subprocess
import sys

from amw_demo.cli import main as cli_main

EXAMPLE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "examples", "five_gate.py"
)
ISSUER = "urn:amw-demo:local-preview"


def _run(tmp_path, *args, env_extra=None):
    env = dict(os.environ)
    env.pop("AMW_DEMO_APPROVAL", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, EXAMPLE, "--out", str(tmp_path), *args],
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=60,
    )


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_approve_makes_one_call_and_verifies(tmp_path):
    proc = _run(tmp_path, "--approve")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    for n in range(1, 6):
        assert f"[GATE {n}/5]" in proc.stdout
    assert "tools/call received 1" in proc.stdout
    assert "[GATE 5/5] evidence: PASS" in proc.stdout
    receipt = os.path.join(str(tmp_path), "receipt.json")
    tampered = os.path.join(str(tmp_path), "receipt.tampered.json")
    keys = os.path.join(str(tmp_path), "trust-keys.json")
    assert cli_main(["verify", receipt, "--keys", keys, "--issuer", ISSUER]) == 0
    assert cli_main(["verify", tampered, "--keys", keys, "--issuer", ISSUER]) == 1
    claims = json.loads(_read(receipt)["signing_input"])
    assert claims["credits_charged"] == "1"
    assert claims["approval_id"].startswith("approval-local-")


def test_no_private_key_written(tmp_path):
    _run(tmp_path, "--approve")
    for name in os.listdir(str(tmp_path)):
        with open(os.path.join(str(tmp_path), name), encoding="utf-8") as handle:
            text = handle.read().lower()
        assert "private" not in text


def test_deny_flag_stops_before_call(tmp_path):
    proc = _run(tmp_path, "--deny")
    assert proc.returncode == 3
    assert "[GATE 3/5] human approval: DENIED" in proc.stdout
    assert "0 MCP calls made, 0 credits charged" in proc.stdout
    assert "[GATE 4/5]" not in proc.stdout
    assert not os.path.exists(os.path.join(str(tmp_path), "receipt.json"))


def test_env_deny_and_default_deny(tmp_path):
    assert _run(tmp_path, env_extra={"AMW_DEMO_APPROVAL": "deny"}).returncode == 3
    assert _run(tmp_path).returncode == 3  # no tty, no flag: deny


def test_env_approve(tmp_path):
    assert _run(tmp_path, env_extra={"AMW_DEMO_APPROVAL": "approve"}).returncode == 0


def test_budget_gate_refuses_before_call(tmp_path):
    proc = _run(tmp_path, "--approve", "--cost", "6", "--max-credits", "5")
    assert proc.returncode == 1
    assert "[GATE 2/5] limits: REFUSED. budget_exceeded" in proc.stdout
    assert "[GATE 4/5]" not in proc.stdout


def test_expiry_gate_refuses_before_call(tmp_path):
    proc = _run(tmp_path, "--approve", "--ttl", "0")
    assert proc.returncode == 1
    assert "permit_expired" in proc.stdout
    assert "[GATE 4/5]" not in proc.stdout

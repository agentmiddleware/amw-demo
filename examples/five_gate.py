"""Five-gate example (Preview): one MCP tool call through five gates.

Runs fully local and offline by default. No API key, no hosted API, no
network. It shows the shape of an AMW governed call on your own machine:

  Gate 1  Identity and scope: a signed permit names the wallet and the one
          allowed tool, and the permit signature is checked.
  Gate 2  Limits: a credit budget and an expiry, both checked before the call.
  Gate 3  Human approval: an explicit local approve or deny step. Deny stops
          here, before any tool call, and charges nothing.
  Gate 4  The governed call: exactly one MCP ``tools/call`` to a local stdio
          MCP server (examples/echo_mcp_server.py).
  Gate 5  Evidence: an Ed25519 signed receipt that is verified offline, plus a
          tampered copy that must fail verification.

Preview only. This is a local illustration of the flow, not the hosted AMW
gateway, and it makes no production, compliance or security guarantee. The
Ed25519 keypair is generated fresh in memory on every run. The private key is
never written to disk; only the public key is saved to trust-keys.json.

Approval, in order of precedence:
  --approve or --deny flag,
  else AMW_DEMO_APPROVAL=approve|deny in the environment,
  else an interactive y/N prompt if stdin is a terminal (default is No),
  else deny.

Exit codes: 0 approved, called and verified; 3 denied (no call, no charge);
1 a gate refused the call or verification did not behave as expected.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
TOOL = "partner.echo"
ISSUER = "urn:amw-demo:local-preview"
KID = "local-preview-ephemeral-ed25519"
DEFAULT_OUT = os.path.join(REPO_ROOT, "five_gate_out")
OUTPUT_FILES = (
    "permit.json",
    "receipt.json",
    "receipt.tampered.json",
    "trust-keys.json",
)


def canonical(obj) -> str:
    """Sorted key compact JSON, the same shape as awi-canonical-json/1."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def gate(number: int, name: str, status: str, detail: str) -> None:
    print(f"[GATE {number}/5] {name}: {status}. {detail}")


# Gate 1
def issue_permit(signing_key, wallet_id: str, max_credits: str, ttl_seconds: int):
    """Issue a signed permit scoped to one wallet and one tool."""
    body = {
        "permit_id": f"permit-local-{uuid.uuid4().hex[:12]}",
        "issuer": ISSUER,
        "subject_wallet_id": wallet_id,
        "allowed_tools": [TOOL],
        "scopes": [f"tool:{TOOL}:invoke", "billing:charge"],
        "max_credits": max_credits,
        "expires_at": (now_utc() + datetime.timedelta(seconds=ttl_seconds)).isoformat(),
        "kid": KID,
    }
    signature = signing_key.sign(canonical(body).encode("utf-8"))
    return {"permit": body, "signature": b64(signature)}


def check_identity_and_scope(signed_permit: dict, public_key, wallet_id: str,
                             tool: str) -> str | None:
    """Gate 1. Return a refusal reason, or None if the permit covers this call."""
    from cryptography.exceptions import InvalidSignature

    body = signed_permit["permit"]
    try:
        public_key.verify(
            base64.b64decode(signed_permit["signature"]),
            canonical(body).encode("utf-8"),
        )
    except InvalidSignature:
        return "permit_signature_invalid"
    if body["subject_wallet_id"] != wallet_id:
        return "permit_wallet_mismatch"
    if tool not in body["allowed_tools"]:
        return "tool_not_allowed"
    if f"tool:{tool}:invoke" not in body["scopes"] or "billing:charge" not in body["scopes"]:
        return "scope_missing"
    return None


# Gate 2
def check_limits(permit: dict, cost: Decimal, spent: Decimal) -> str | None:
    """Gate 2. Budget cap and expiry, both checked before any call."""
    expires_at = datetime.datetime.fromisoformat(permit["expires_at"])
    if now_utc() >= expires_at:
        return "permit_expired"
    if spent + cost > Decimal(permit["max_credits"]):
        return "budget_exceeded"
    return None


# Gate 3
def resolve_approval(args) -> tuple[bool, str]:
    """Gate 3. Explicit local human approval. Anything unclear means deny."""
    if args.approve:
        return True, "--approve flag"
    if args.deny:
        return False, "--deny flag"
    env = os.environ.get("AMW_DEMO_APPROVAL", "").strip().lower()
    if env in ("approve", "deny"):
        return env == "approve", f"AMW_DEMO_APPROVAL={env}"
    if sys.stdin.isatty():
        answer = input(f"Approve one call to {TOOL}? [y/N] ").strip().lower()
        return answer in ("y", "yes"), f"interactive prompt answered {answer or 'N'!r}"
    return False, "no approval given and stdin is not a terminal"


# Gate 4
def call_mcp_tool_once(tool: str, arguments: dict) -> tuple[dict, str]:
    """Gate 4. Start the local MCP server and make exactly one tools/call."""
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "echo_mcp_server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def rpc(msg_id, method, params):
        proc.stdin.write(canonical(
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        ) + "\n")
        proc.stdin.flush()
        reply = json.loads(proc.stdout.readline())
        if "error" in reply:
            raise RuntimeError(f"MCP {method} failed: {reply['error']}")
        return reply["result"]

    try:
        rpc(1, "initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "amw-demo-five-gate", "version": "0.1.0"},
        })
        proc.stdin.write(canonical(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        ) + "\n")
        result = rpc(2, "tools/call", {"name": tool, "arguments": arguments})
    finally:
        proc.stdin.close()
        server_log = proc.stderr.read().strip()
        proc.wait(timeout=10)
    return result, server_log


# Gate 5
def sign_receipt(signing_key, claims: dict) -> dict:
    """Gate 5. Sign a receipt in the same portable shape amw-demo verify reads."""
    claims = dict(claims, alg="Ed25519", kid=KID)
    claims["payload_hash"] = sha256_hex(canonical(claims))
    signing_input = canonical(claims)
    return {
        "alg": "Ed25519",
        "canonicalization": "awi-canonical-json/1",
        "issuer": ISSUER,
        "kid": KID,
        "receipt_id": claims["receipt_id"],
        "schema_version": "preview-local",
        "signature": b64(signing_key.sign(signing_input.encode("utf-8"))),
        "signing_input": signing_input,
    }


def tamper(receipt: dict) -> dict:
    """Return a copy with credits_charged edited after signing."""
    claims = json.loads(receipt["signing_input"])
    claims["credits_charged"] = "0"
    return dict(receipt, signing_input=canonical(claims))


def write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true", help="approve the call")
    decision.add_argument("--deny", action="store_true", help="deny the call")
    parser.add_argument("--out", default=os.environ.get("AMW_DEMO_OUT", DEFAULT_OUT),
                        help="output directory (default: ./five_gate_out)")
    parser.add_argument("--cost", default="1", help="credits this call costs")
    parser.add_argument("--max-credits", default="5", help="permit budget cap")
    parser.add_argument("--ttl", type=int, default=900, help="permit expiry, seconds")
    args = parser.parse_args(argv)

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    from amw_demo.verify import verify_receipt

    wallet_id = os.environ.get("AMW_WALLET_ID") or "wallet-local-preview"
    cost = Decimal(args.cost)
    spent = Decimal(0)
    os.makedirs(args.out, exist_ok=True)
    for name in OUTPUT_FILES:
        path = os.path.join(args.out, name)
        if os.path.exists(path):
            os.remove(path)

    print("AMW five-gate example (Preview, local offline mode, no hosted API)")
    signing_key = Ed25519PrivateKey.generate()  # in memory only, never saved
    public_key = signing_key.public_key()
    public_raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    trust_keys = {
        "alg": "Ed25519",
        "issuer": ISSUER,
        "keys": [{"alg": "Ed25519", "kid": KID, "public_key_b64": b64(public_raw),
                  "status": "active"}],
    }
    keys_path = os.path.join(args.out, "trust-keys.json")
    write_json(keys_path, trust_keys)
    print(f"Generated a fresh Ed25519 keypair for this run (kid {KID}). "
          f"Public key saved to {keys_path}; private key stays in memory.")

    # Gate 1: identity and scope
    signed_permit = issue_permit(signing_key, wallet_id, args.max_credits, args.ttl)
    write_json(os.path.join(args.out, "permit.json"), signed_permit)
    permit = signed_permit["permit"]
    refusal = check_identity_and_scope(signed_permit, public_key, wallet_id, TOOL)
    if refusal:
        gate(1, "identity and scope", "REFUSED", refusal)
        return 1
    gate(1, "identity and scope", "PASS",
         f"Permit {permit['permit_id']} signature valid; wallet {wallet_id}; "
         f"allowed tools {permit['allowed_tools']}.")

    # Gate 2: limits
    refusal = check_limits(permit, cost, spent)
    if refusal:
        gate(2, "limits", "REFUSED", f"{refusal}. No call made, 0 credits charged.")
        return 1
    gate(2, "limits", "PASS",
         f"Cost {cost} within budget {permit['max_credits']} (spent {spent}); "
         f"expires {permit['expires_at']}.")

    # Gate 3: human approval
    approved, source = resolve_approval(args)
    if not approved:
        gate(3, "human approval", "DENIED",
             f"Decision from {source}. Stopped before the tool call: 0 MCP calls "
             f"made, 0 credits charged, budget still {permit['max_credits']}.")
        return 3
    approval_id = f"approval-local-{uuid.uuid4().hex[:12]}"
    gate(3, "human approval", "APPROVED", f"Decision from {source} ({approval_id}).")

    # Gate 4: the single governed MCP tool call
    arguments = {"message": "hello from the AMW five-gate example"}
    request_hash = sha256_hex(canonical({
        "tool_name": TOOL, "arguments": arguments,
        "wallet_id": wallet_id, "permit_id": permit["permit_id"],
    }))
    result, server_log = call_mcp_tool_once(TOOL, arguments)
    if result.get("isError"):
        gate(4, "governed call", "FAILED", "tool reported isError true")
        return 1
    spent += cost
    gate(4, "governed call", "DONE",
         f"One MCP tools/call to {TOOL} returned {result.get('structuredContent')}. "
         f"Server log: {server_log}. Charged {cost}, budget left "
         f"{Decimal(permit['max_credits']) - spent}.")

    # Gate 5: evidence
    receipt = sign_receipt(signing_key, {
        "receipt_id": f"rcpt-local-{uuid.uuid4().hex[:16]}",
        "permit_id": permit["permit_id"],
        "wallet_id": wallet_id,
        "tool": TOOL,
        "request_hash": request_hash,
        "response_hash": sha256_hex(canonical(result)),
        "credits_authorized": permit["max_credits"],
        "credits_charged": str(cost),
        "outcome": "success",
        "approval_id": approval_id,
        "created_at": now_utc().isoformat(),
    })
    receipt_path = os.path.join(args.out, "receipt.json")
    tampered_path = os.path.join(args.out, "receipt.tampered.json")
    write_json(receipt_path, receipt)
    write_json(tampered_path, tamper(receipt))
    del signing_key  # nothing else can be signed this run

    good = verify_receipt(receipt, trust_keys, expected_issuer=ISSUER)
    bad = verify_receipt(tamper(receipt), trust_keys, expected_issuer=ISSUER)
    print(f"   Offline verify {receipt_path}: {'PASS' if good.ok else 'FAIL'} "
          f"({good.reason})")
    print(f"   Offline verify {tampered_path} (credits_charged edited): "
          f"{'PASS' if bad.ok else 'FAIL'} ({bad.reason})")
    if not good.ok or bad.ok:
        gate(5, "evidence", "FAILED", "verification did not behave as expected")
        return 1
    gate(5, "evidence", "PASS",
         f"Receipt {receipt['receipt_id']} verifies offline; tampered copy fails.")
    print("Done. 1 MCP tool call, 1 signed receipt. Preview only: a local "
          "illustration, not the hosted gateway.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

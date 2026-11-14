# amw-demo

Agent Middleware (AMW) is a hosted gateway that sits between AI agents and the tools they call. An agent gets a signed permit that scopes what it may do, calls the tool through the gateway, and gets back a signed receipt that can be checked offline against the published public key. This repo shows that loop in a few minutes using only the public API.

## Quickstart (under 5 minutes)

Needs Python 3.10 or newer.

```bash
git clone https://github.com/agentmiddleware/amw-demo.git
cd amw-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

No key needed, verify the published receipt:

```bash
python examples/verify_published_receipt.py
```

That downloads a real portable receipt and key snapshot published at
https://www.agentmiddleware.dev/proof/ and checks the signature offline.
Fully offline alternative:

```bash
python examples/verify_published_receipt.py --offline
```

Get a free demo key (no account needed) at
https://www.agentmiddleware.dev/demo-key/ or from a terminal:

```bash
curl -s -X POST https://api.thisisatest.tech/v1/demo/keys
```

The response includes `api_key` and `wallet_id`.

Have a key? Run the full loop:

```bash
export AMW_API_KEY='<your key>'
export AMW_WALLET_ID='<your wallet id>'
python examples/permit_echo_retry.py
```

You can also verify any receipt file directly:

```bash
python -m amw_demo verify receipt.json --keys trust-keys.json [--issuer URL]
```

After `pip install -e .` the `amw-demo` console script is installed, so
`amw-demo verify receipt.json --keys trust-keys.json` works the same way.

Exit code 0 means verified, 1 means signature invalid, 2 means it cannot
be determined (for example an unknown key id or an unreadable file).

## Five-gate example (Preview)

Preview only. `examples/five_gate.py` makes exactly one MCP tool call and
walks it through five gates on your own machine. It runs fully local and
offline: no API key, no account and no hosted API. The tool is a tiny stdio
MCP server in this repo (`examples/echo_mcp_server.py`) that echoes its input,
so there is no real side effect. This is a local illustration of the flow, not
the hosted gateway, and it is not a production, compliance or security claim.

| Gate | Where | What it shows |
| --- | --- | --- |
| 1. Identity and scope | `issue_permit`, `check_identity_and_scope` | A permit signed with Ed25519 names the wallet and the one allowed tool and its scopes. The signature, wallet, tool and scopes are checked. |
| 2. Limits | `check_limits` | A credit budget cap and an expiry are both checked before any call. |
| 3. Human approval | `resolve_approval` | An explicit local approve or deny step. Deny stops before the call: no MCP call, nothing charged. |
| 4. Governed call | `call_mcp_tool_once` | One MCP `tools/call` over stdio JSON-RPC. The server reports how many calls it received. |
| 5. Evidence | `sign_receipt`, `amw_demo.verify.verify_receipt` | An Ed25519 signed receipt that verifies offline (PASS), and a copy with `credits_charged` edited after signing that fails (FAIL). |

A fresh Ed25519 keypair is generated in memory on every run. The private key
is never written to disk. Only the public key is saved, to
`five_gate_out/trust-keys.json`. Nothing in this repo holds a key.

Install (Python 3.10 or newer):

```bash
git clone https://github.com/agentmiddleware/amw-demo.git
cd amw-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Approve run (one call, receipt verified offline, tampered copy fails):

```bash
python examples/five_gate.py --approve
echo "exit $?"
```

Expected output (ids, timestamps and paths differ on every run):

```text
AMW five-gate example (Preview, local offline mode, no hosted API)
Generated a fresh Ed25519 keypair for this run (kid local-preview-ephemeral-ed25519). Public key saved to .../five_gate_out/trust-keys.json; private key stays in memory.
[GATE 1/5] identity and scope: PASS. Permit permit-local-... signature valid; wallet wallet-local-preview; allowed tools ['partner.echo'].
[GATE 2/5] limits: PASS. Cost 1 within budget 5 (spent 0); expires ...
[GATE 3/5] human approval: APPROVED. Decision from --approve flag (approval-local-...).
[GATE 4/5] governed call: DONE. One MCP tools/call to partner.echo returned {'echo': 'hello from the AMW five-gate example'}. Server log: echo_mcp_server: tools/call received 1. Charged 1, budget left 4.
   Offline verify .../five_gate_out/receipt.json: PASS (signature valid)
   Offline verify .../five_gate_out/receipt.tampered.json (credits_charged edited): FAIL (signature invalid: bytes do not match the signing_input)
[GATE 5/5] evidence: PASS. Receipt rcpt-local-... verifies offline; tampered copy fails.
Done. 1 MCP tool call, 1 signed receipt. Preview only: a local illustration, not the hosted gateway.
exit 0
```

Deny run (stops at gate 3, no call, nothing charged, exit code 3):

```bash
python examples/five_gate.py --deny
echo "exit $?"
```

Expected output:

```text
AMW five-gate example (Preview, local offline mode, no hosted API)
Generated a fresh Ed25519 keypair for this run (kid local-preview-ephemeral-ed25519). Public key saved to .../five_gate_out/trust-keys.json; private key stays in memory.
[GATE 1/5] identity and scope: PASS. Permit permit-local-... signature valid; wallet wallet-local-preview; allowed tools ['partner.echo'].
[GATE 2/5] limits: PASS. Cost 1 within budget 5 (spent 0); expires ...
[GATE 3/5] human approval: DENIED. Decision from --deny flag. Stopped before the tool call: 0 MCP calls made, 0 credits charged, budget still 5.
exit 3
```

With no flag, the example asks `Approve one call to partner.echo? [y/N]` in a
terminal, and the default is No. You can also set `AMW_DEMO_APPROVAL=approve`
or `AMW_DEMO_APPROVAL=deny`. With no flag, no variable and no terminal, it
denies.

Verify the receipt from the approve run yourself, offline, with the existing
verifier (exit 0 is verified, 1 is signature invalid):

```bash
amw-demo verify five_gate_out/receipt.json --keys five_gate_out/trust-keys.json --issuer urn:amw-demo:local-preview
echo "exit $?"
amw-demo verify five_gate_out/receipt.tampered.json --keys five_gate_out/trust-keys.json --issuer urn:amw-demo:local-preview
echo "exit $?"
```

Expected output:

```text
Verified receipt rcpt-local-... (tool partner.echo, outcome success, kid local-preview-ephemeral-ed25519).
exit 0
Verification failed: signature invalid: bytes do not match the signing_input
exit 1
```

What this example does not show: it runs no hosted gateway, ledger or audit
chain, and the keypair exists only for one run. The receipt signs hashes of
the request and the tool result, not the content, and does not prove the tool
output was correct. The approval here is a local prompt or flag; on the hosted
gateway a human approval gate is optional. For the hosted loop with a demo key
(permit, governed call, same key retry, offline check), use
`examples/permit_echo_retry.py` above. The Limits section below still applies.

## What the full loop example proves, and what it does not

The example creates a temporary permit scoped to `partner.echo`, calls
the tool, retries with the same idempotency key and arguments, then
verifies the receipt offline. It proves three things:

1. A scoped permit authorizes one governed call within a small budget.
2. A retry with the same key returns the original receipt instead of dispatching again. A new key is a new request.
3. The receipt signature checks out offline against the published keys.

It does not prove the tool output was correct. Receipts sign hashes of the
request and response, not the content itself. It also says nothing about
calls that have no receipt: a missing receipt proves nothing. `partner.echo`
is a reference tool that only echoes its input back, so there is no real
side effect here.

## Getting a key

The demo key page https://www.agentmiddleware.dev/demo-key/ issues demo keys
through `POST /v1/demo/keys` (demo tenant, synthetic credits,
no account needed). Export the key as
`AMW_API_KEY` to run the full loop. If `AMW_API_KEY` is missing,
the example prints these instructions and exits without making any
authenticated calls. The published receipt check above works today with no key.

## Limits

These apply to AMW itself, not just this demo:

- The retry behavior above holds per idempotency key at the gateway. It does not make a remote side effect happen only once on its own: that also depends on the tool honoring the forwarded key (sent in the MCP call metadata), and a retry under a new key is always a new call. Permit call limits are optional and off by default.
- A call can end in a `delivery_uncertain` state: charged, outcome unknown, and never sent again automatically. Someone has to reconcile it against the upstream tool.
- Receipts sign hashes, not content, and do not prove the tool was right. Signing uses a single key held by the operator, offline verification trusts the issuing origin for key distribution, and there is no external transparency log.
- The wallet audit chain provides evidence of tampering, but does not prevent it. The ledger itself is not linked by hashes. Database administrators could still rewrite rows.
- Pilot scope: governed MCP calls only, through one configured upstream tool. There is no claim of isolation between tenants.

## Links

- Interactive docs: https://api.thisisatest.tech/docs
- OpenAPI spec: https://api.thisisatest.tech/openapi.json
- Agent docs: https://api.thisisatest.tech/llms.txt
- Security limitations: https://api.thisisatest.tech/SECURITY_LIMITATIONS.md

This repo speaks only to the public API above. It bundles no private code
and needs no private access except a demo key from the demo key page for
the full loop.

## License

Apache 2.0 (gateway is Fair Source, FSL-1.1)

See [LICENSE](LICENSE) and [NOTICE](NOTICE). The gateway source is at
https://github.com/agentmiddleware/agent-middleware.

# amw-demo

Agent Middleware (AMW) is a hosted gateway that sits between AI agents and the tools they call. An agent gets a signed permit that scopes what it may do, calls the tool through the gateway, and gets back a signed receipt that anyone can check offline. This repo shows that loop in a few minutes using only the public API.

## Quickstart (under 5 minutes)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

No key needed, verify the published receipt:

```bash
python examples/verify_published_receipt.py
```

That downloads a real portable receipt and key snapshot published at
https://www.thisisatest.tech/proof/ and checks the signature offline.
Fully offline alternative:

```bash
python examples/verify_published_receipt.py --offline
```

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

Exit code 0 means verified, 1 means signature invalid, 2 means it cannot
be determined (for example an unknown key id or an unreadable file).

## What the full-loop example proves, and what it does not

The example creates a short-lived permit scoped to `partner.echo`, calls
the tool, retries with the same idempotency key and arguments, then
verifies the receipt offline. It proves three things:

1. A scoped permit authorizes one governed call within a small budget.
2. A retry with the same idempotency key and the same request returns the original signed receipt. The tool is not called again and the wallet is not charged again. A new key is a new call.
3. The receipt signature checks out offline against the published keys.

It does not prove the tool output was correct. Receipts sign hashes of the
request and response, not the content itself. It also says nothing about
calls that have no receipt: a missing receipt proves nothing. `partner.echo`
is a reference tool that only echoes its input back, so there is no real
side effect here.

## Getting a key

There is no public self-serve key today, and the tool catalog, permits,
invoke, and receipt export all return 401 without an operator-issued key.
To run the full loop, ask the operator for a wallet-scoped key as described
in [KEY_PATH_PROPOSAL.md](KEY_PATH_PROPOSAL.md). If `AMW_API_KEY` is missing,
the example prints these instructions and exits without making any
authenticated calls.

## Limits

These apply to AMW itself, not just this demo:

- The retry behavior above holds per idempotency key at the gateway. It does not make a remote side effect happen only once on its own: that also depends on the tool honoring the forwarded key (sent in the MCP call metadata), and a retry under a new key is always a new call. Permit call limits are optional and off by default.
- A call can end in a `delivery_uncertain` state: charged, outcome unknown, and never re-sent automatically. Someone has to reconcile it against the upstream tool.
- Receipts sign hashes, not content, and do not prove the tool was right. Signing uses a single operator-held key, offline verification trusts the issuing origin for key distribution, and there is no external transparency log.
- The wallet audit chain is tamper-evident, not tamper-proof, and the ledger itself is not hash-chained. Database administrators could still rewrite rows.
- Pilot scope: governed MCP calls only, through one configured upstream tool. There is no multi-tenant isolation claim.

## Links

- Interactive docs: https://api.thisisatest.tech/docs
- OpenAPI spec: https://api.thisisatest.tech/openapi.json
- Agent docs: https://api.thisisatest.tech/llms.txt
- Security limitations: https://api.thisisatest.tech/SECURITY_LIMITATIONS.md

This repo speaks only to the public API above. It bundles no private code
and needs no private access except the operator-issued key for the full loop.

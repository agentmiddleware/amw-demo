# Proposal: demo keys for the full-loop example

Demo readers cannot run `examples/permit_echo_retry.py` today without asking
the operator for a key by hand. This note proposes the smallest safe way to
let them try it. It changes nothing in the API; everything framed as a code
change below is a proposal for the private API, not a change made here.

## What exists today

From the public bootstrap doc served by the API:

- There is no public self-serve key mint. The operator provisions a sponsor wallet, an agent wallet, and a wallet-scoped agent key, then hands the key and wallet id to the partner over a secure channel.
- The operator can already bound a minted key: `--daily-limit` caps daily spend in credits, `--expires-in-days` stops the key after N days, and `--max-uses` stops it after N successful authentications, enforced server-side.
- Authenticated routes are rate limited (default 120 requests per minute per key).
- A key can be revoked when the engagement ends.

What does not exist today: a way to scope the key itself to one tool. The
permit carries `allowed_tools` and scopes, but the key is wallet-scoped, so
a demo key could in principle mint permits for other tools or larger budgets.

## Recommended setup (no API change needed)

1. The operator provisions one demo sponsor wallet and one agent wallet per reader (or one shared demo wallet with a low balance, if per-reader wallets are too much work).
2. Mint each demo key with tight bounds: a small credit budget, a low `--daily-limit`, a short `--expires-in-days` (a few days), and a small `--max-uses` cap.
3. Issue each demo permit only for `partner.echo`, with `allowed_tools` set to `["partner.echo"]`, scopes limited to `tool:partner.echo:invoke` and `billing:charge`, a small `max_credits` value, and an expiry minutes ahead. `partner.echo` only echoes its input back, so a demo call has no real side effect.
4. Hand keys out per person on request, over a private channel, and revoke them when the demo window ends. If per-person keys are too much work, a rotating shared key with the same bounds is the fallback: rotate it on a schedule and revoke on any sign of abuse.

## Proposed API hardening (for the private API, not this repo)

These would make demo keys safer to hand out. Each is a proposal:

- A key-level tool allowlist, so the key itself cannot touch anything but `partner.echo`, even if someone crafts a broader permit request.
- A flag on demo wallets that blocks permit creation for other tools or for budgets above a small ceiling, enforced before any reservation or dispatch.
- A separate demo tenant (own wallets, own budget pool), so demo traffic cannot spend partner funds or mix into partner audit chains.
- Automated key rotation and expiry reminders, so stale demo keys stop working without manual cleanup.
- Abuse monitoring on demo wallets: alert on spend velocity, permit volume, or repeated 401 and 403 responses, and freeze on thresholds already used for wallets.

Until those exist, keep demo bounds small, windows short, and issuance manual.

## What we need from the operator

- Decide whether demo readers get per-person keys issued on request or share one rotating key.
- Pick the bounds for demo keys: credit budget, daily limit, expiry, and max uses.
- Confirm `partner.echo` is registered and reachable in production for demo wallets.

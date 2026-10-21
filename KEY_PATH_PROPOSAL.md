# Historical proposal: demo keys for the full loop example

This note proposed manual key issuance before `POST /v1/demo/keys` became
available. For the current demo key flow, see the Getting a key section of
the README. The API changes below were proposals, not changes made here.

## Historical state

At the time of this proposal, the public bootstrap doc said:

- The operator provisioned a sponsor wallet, an agent wallet, and an agent key scoped to a wallet, then handed the key and wallet id to the partner over a secure channel.
- The operator could bound a minted key: `--daily-limit` capped daily spend in credits, `--expires-in-days` stopped the key after N days, and `--max-uses` stopped it after N successful authentications, enforced by the server.
- Authenticated routes were rate limited (default 120 requests per minute per key).
- A key could be revoked when the engagement ended.

At the time, there was no way to scope the key itself to one tool. The
permit carried `allowed_tools` and scopes, but the key was scoped to a wallet,
so a demo key could in principle mint permits for other tools or larger budgets.

## Historical recommended setup

1. The operator provisions one demo sponsor wallet and one agent wallet per reader (or one shared demo wallet with a low balance, if separate wallets for each reader are too much work).
2. Mint each demo key with tight bounds: a small credit budget, a low `--daily-limit`, a short `--expires-in-days` (a few days), and a small `--max-uses` cap.
3. Issue each demo permit only for `partner.echo`, with `allowed_tools` set to `["partner.echo"]`, scopes limited to `tool:partner.echo:invoke` and `billing:charge`, a small `max_credits` value, and an expiry minutes ahead. `partner.echo` only echoes its input back, so a demo call has no real side effect.
4. Hand keys out per person on request, over a private channel, and revoke them when the demo window ends. If separate keys for each person are too much work, a rotating shared key with the same bounds is the fallback: rotate it on a schedule and revoke on any sign of abuse.

## Historical API hardening proposals

These would make demo keys safer to hand out. Each is a proposal:

- A tool allowlist on each key, so the key itself cannot touch anything but `partner.echo`, even if someone crafts a broader permit request.
- A flag on demo wallets that blocks permit creation for other tools or for budgets above a small ceiling, enforced before any reservation or dispatch.
- A separate demo tenant (own wallets, own budget pool), so demo traffic cannot spend partner funds or mix into partner audit chains.
- Automated key rotation and expiry reminders, so stale demo keys stop working without manual cleanup.
- Abuse monitoring on demo wallets: alert on spend velocity, permit volume, or repeated 401 and 403 responses, and freeze on thresholds already used for wallets.

This manual issuance plan was superseded by the live demo key flow.

## Historical operator decisions

- Decide whether demo readers get separate keys issued on request or share one rotating key.
- Pick the bounds for demo keys: credit budget, daily limit, expiry, and max uses.
- Confirm `partner.echo` is registered and reachable in production for demo wallets.

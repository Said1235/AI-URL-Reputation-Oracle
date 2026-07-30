# Use case: Wallets — block links before opening them

> From the original spec: *"Wallets: before opening a link."*

When a wallet shows an external link (an NFT's metadata, a connected
dApp's site, a link pasted by the user), this pattern passes it through
the oracle before letting it open.

## Files

- `linkGuard.ts` — pure logic: `guardExternalLink(url)` returns
  `{ action: "open" | "warn" | "block", report }`.
- `useLinkGuard.example.tsx` — React hook + example button component, to
  copy into a real app.

## Flow

1. User clicks an external link.
2. `guardExternalLink` calls `has_report(url)`. If it was never analyzed,
   it triggers `analyze(url)` (on-chain transaction, waits for consensus)
   and then reads `get_report(url)`.
3. Based on the result's `risk_tier` — the field consensus actually gates
   on, not the informational `trust_score`:
   - `"high_risk"` → **block** (doesn't open, shows an alert).
   - `"caution"` → **warn** (confirmation before opening).
   - `"trusted"` → **open** (opens directly).

## Production considerations

- **Decide on `risk_tier`, never on `trust_score`.** `risk_tier` is the
  field GenLayer's validator consensus is actually gated on (leader and
  every validator had to independently land in the exact same bucket).
  `trust_score` is stored for display only and can legitimately differ
  between two equally-valid accepted analyses of the same site — using
  it to drive an automated decision reintroduces the exact problem this
  oracle's consensus design was fixed to prevent.
- **Don't generate a fresh account on every call.** The example uses
  `createWriteClient()` with no arguments (generates an account on the
  fly) only so the snippet runs standalone. In a real wallet, that
  service account must be fixed and live in a backend/relay — never
  embedded in the client bundle.
- **The first time a URL is seen, there's real latency** (web fetch + LLM,
  twice: once for the leader and once for each validator verifying it).
  Always show a loading state ("Analyzing link...") instead of silently
  blocking the UI.
- Consider caching the `get_report` result client-side for a short time
  to avoid re-reading the contract on every render.

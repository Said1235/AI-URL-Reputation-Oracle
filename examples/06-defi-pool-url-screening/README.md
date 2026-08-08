# Use case: DeFi protocols — screening pool/project URLs

> From the original spec: *"DeFi protocols: automatically evaluate URLs
> associated with pools or projects before showing them to users."*

`screen_pool_urls.py` is a backend job (Python + `genlayer-py`) meant to
run periodically (cron / pipeline) over a protocol's list of active pools,
producing a filtered list ready for the frontend to consume.

## What it does

1. Reads `pools.json` with the list of pools and their declared
   `projectUrl`.
2. For each one, runs `ensure_analyzed` against the oracle.
3. Writes two files:
   - `pools-displayable.json`: pools bucketed `risk_tier == "trusted"` —
     the field GenLayer's validator consensus is actually gated on. This
     is deliberately not re-derived from `safe`/`phishing`/`malware`
     directly: a pool can be `safe: true` with a mediocre `trust_score`
     that the oracle itself buckets as `caution`, and that shouldn't be
     shown to users without review just because no explicit danger flag
     tripped.
   - `pools-flagged.json`: everything else (`caution` or `high_risk`),
     for manual review before deciding whether to hide them or show them
     with a warning.

## Usage

```bash
pip install -r ../requirements.txt
export ORACLE_CONTRACT_ADDRESS=0x...
python screen_pool_urls.py pools.json
```

## Why a periodic job instead of a real-time call

Unlike the explorer badge (`02-explorer-trust-badge`, which reads on every
render), a DeFi protocol usually already has a relatively stable pool
list. Running this script as a cron (e.g. every 6-24 hours) and serving
`pools-displayable.json` from your own API/cache avoids:

- Paying the cost of re-analyzing a URL on every user request.
- Blocking the frontend's render while waiting for validator consensus.

If you need real-time verification for pools created dynamically, combine
this job with a one-off call to `ensure_analyzed` in the pool-creation
flow (similar to the pattern in `05-launchpad-presale-guard`).

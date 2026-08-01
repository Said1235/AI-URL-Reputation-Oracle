# Use case: DAOs — verify links in governance proposals

> From the original spec: *"DAOs: verify links included in governance
> proposals."*

`scan_proposal_links.py` is a backend script (Python + `genlayer-py`)
meant to run automatically every time a new proposal is created in the
DAO (as a bot/webhook, or as a manual step before publishing it).

## What it does

1. Extracts every URL from the proposal's text (simple regex, no external
   dependencies).
2. Runs each one against the oracle (`ensure_analyzed`: analyzes if there's
   no prior report, otherwise just reads it).
3. If any URL's `risk_tier` isn't `"trusted"` — the field GenLayer's
   validator consensus is actually gated on — marks the proposal as
   **pending manual review** instead of letting it move straight to
   voting. This deliberately doesn't re-derive its own condition from
   `phishing`/`malware`/`safe`: a site can be `safe: true` with a
   mediocre `trust_score` that the oracle itself buckets as `caution`,
   and that should still get a human's eyes on it before a DAO vote opens.

## Usage

```bash
pip install -r ../requirements.txt
export ORACLE_CONTRACT_ADDRESS=0x...
python scan_proposal_links.py proposal.txt
```

Exit code (useful for integrating into a pipeline/CI/webhook):

- `0` → all URLs passed the analysis, the proposal can proceed.
- `2` → some URLs are flagged, requires manual review before opening the
  vote.

## Note on the network

This example defaults to `studionet`. Available networks for `genlayer-py`
are `localnet`, `studionet`, `testnet_asimov`, and `testnet_bradbury` (see
`examples/shared_py/oracle_client.py`). Adjust `GENLAYER_CHAIN` in
`examples/shared_py/config.py` or via environment variable depending on
where your DAO operates.

# Use case: NFT marketplaces — validate collection links

> From the original spec: *"Marketplaces: validate NFT collection links."*

Batch moderation script (`validateCollectionLinks.ts`): takes a JSON file
with collections pending approval and their declared website, runs each
URL against the oracle, and produces two outputs:

- Console: summary + list of collections not approved (`risk_tier` is
  `caution` or `high_risk`).
- `collection-validation-results.json`: full detail for all collections
  (approved and not), with each one's `trustScore`, `riskTier`,
  `category`, and `reason`, to feed a moderation dashboard.

## Usage

```bash
npm install
npx tsx validateCollectionLinks.ts collections.json
```

Example `collections.json`:

```json
[
  { "collectionId": "azuki", "website": "https://azuki.com" },
  { "collectionId": "fake-boredapes", "website": "https://claim-bayc-airdrop.xyz" }
]
```

## Notes

- The script processes collections **sequentially**, not in parallel:
  every `analyze()` without a prior report waits for validator consensus,
  and parallelizing doesn't speed it up (same validator set).
- `approved` is `true` only when `risk_tier === "trusted"` — the field
  GenLayer's validator consensus is actually gated on. It's intentionally
  **not** derived from a hand-picked combination of raw fields like
  `safe && !phishing && !malware`: a site can be `safe: true` with a
  mediocre `trust_score` that the oracle itself buckets as `caution`, and
  approving it anyway would reintroduce the same inconsistency this
  repo's consensus design was fixed to eliminate. If you want a looser or
  stricter marketplace policy, adjust the oracle's tier breakpoints in
  `contracts/url_reputation_oracle.py`, not this script.

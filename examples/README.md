# Integration examples — AI URL Reputation Oracle

Each folder implements one of the use cases listed in the project's
original spec, using the already-deployed contract
(`contracts/url_reputation_oracle.py`) via `genlayer-js` or `genlayer-py`
as appropriate.

| # | Use case | Actor | Folder | Language |
|---|---|---|---|---|
| 1 | Block/warn before opening a link | Wallets | [`01-wallet-link-guard`](./01-wallet-link-guard) | TypeScript |
| 2 | Trust badge next to a URL | Blockchain explorers | [`02-explorer-trust-badge`](./02-explorer-trust-badge) | TypeScript (React) |
| 3 | Validate NFT collection links | Marketplaces | [`03-nft-marketplace-collection-links`](./03-nft-marketplace-collection-links) | TypeScript |
| 4 | Verify links in governance proposals | DAOs | [`04-dao-governance-proposal-scanner`](./04-dao-governance-proposal-scanner) | Python |
| 5 | Detect fraudulent presales | Launchpads | [`05-launchpad-presale-guard`](./05-launchpad-presale-guard) | TypeScript |
| 6 | Screening pool/project URLs | DeFi protocols | [`06-defi-pool-url-screening`](./06-defi-pool-url-screening) | Python |

All of them share two helper layers, so the contract's argument mapping
isn't repeated in every file:

- `shared/` (TypeScript, used by 01, 02, 03, 05): `genlayerClient.ts`
  creates read/write clients via `genlayer-js`; `oracleClient.ts` exposes
  `getReport`, `hasReport`, `analyzeUrl`, `ensureAnalyzed`.
- `shared_py/` (Python, used by 04, 06): the equivalent with `genlayer-py`.

## Setup

### TypeScript (cases 1, 2, 3, 5)

```bash
cd examples
npm install
cp .env.example .env   # fill in ORACLE_CONTRACT_ADDRESS with the real address
```

Each example runs with `npx tsx <file>.ts` (see each folder's README for
the exact command). `02-explorer-trust-badge` is a pure React component —
it's imported into an existing app, not run standalone.

### Python (cases 4, 6)

```bash
cd examples
pip install -r requirements.txt
export ORACLE_CONTRACT_ADDRESS=0x...
export GENLAYER_CHAIN=studionet   # or localnet, testnet_asimov, testnet_bradbury
python 04-dao-governance-proposal-scanner/scan_proposal_links.py proposal.txt
```

## Production considerations (apply to all examples)

- **Service accounts, not accounts on the fly.** The shared helpers
  (`createWriteClient` / `create_write_client`) generate a fresh account
  by default if none is passed — useful so the examples run standalone,
  but in production you need to load a fixed service account (private key
  from a secret manager) so you don't lose transaction history/funds
  between runs, and so transactions can be traced back to a known sender.
- **`analyze()` is a real transaction.** The first time a URL is seen,
  any of these flows triggers `analyze()` and waits for validator
  consensus (web fetch + LLM, run by both the leader and every validator
  verifying it). That has real latency (seconds) and costs gas outside
  StudioNet. The examples meant to run from a public page with no access
  control (like the explorer badge) avoid triggering `analyze()`
  automatically for this reason.
- **Never embed a service private key in a frontend bundle.** The
  wallet/launchpad examples that call `analyze()` from the client are
  illustrative; in production that write should go through a
  backend/relay that controls who can trigger new analyses.
- **Verify the API before extending.** Both shared wrappers only use
  methods confirmed against the real `genlayer-js` / `genlayer-py`
  packages (`createClient`/`create_client`, `readContract`/
  `read_contract`, `writeContract`/`write_contract`,
  `waitForTransactionReceipt`/`wait_for_transaction_receipt`, `chains`).
  If you need something else (staking, events,
  `debugTraceTransaction`, etc.), confirm it in the SDK reference before
  using it.

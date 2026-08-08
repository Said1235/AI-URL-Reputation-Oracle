# AI URL Reputation Oracle

A decentralized reputation oracle for websites and domains, built as an
**Intelligent Contract** on [GenLayer](https://genlayer.com).

Unlike traditional blacklists, this contract uses GenLayer's AI and web
access capabilities to inspect a page's real content and classify its
trust level through **validator consensus**, rather than through a single
centralized provider.

## Problem it solves

Most Web3 applications (wallets, NFT marketplaces, blockchain explorers,
DeFi platforms, DAOs, launchpads, decentralized identity systems) need to
know whether a URL is safe before displaying it or letting a user interact
with it. Today almost all of them depend on a centralized reputation
service. This contract removes that dependency: it's a **reusable
primitive** that any other contract or dApp can query.

Questions it answers:

- Does this domain look like phishing?
- Does this site contain malware?
- Is this the official page for a project?
- Is this a copy/impersonation of another site?
- Is this a fraudulent faucet?
- Does it have good reputation overall?

## How it works

1. The user (or a contract) submits a URL to `analyze(url)`.
2. GenLayer fetches the page's real HTML with `gl.nondet.web.render(url, mode="html")`.
3. An LLM analyzes the HTML (visible text, forms, links, structure,
   suspicious signals) and responds **only** with a structured JSON of
   fixed schema.
4. GenLayer's validators independently re-run the same analysis and
   compare the verdict against the leader's (see
   [Consensus design](#consensus-design)).
5. Once validators reach consensus (Optimistic Democracy), the result is
   persisted on-chain.

### LLM output schema

```json
{
    "phishing": false,
    "malware": false,
    "gambling": false,
    "adult": false,
    "official": true,
    "trust_score": 94,
    "category": "Protocol",
    "reason": "Official protocol website"
}
```

The contract derives two more fields from this before storing anything:
`risk_tier` ("trusted" / "caution" / "high_risk") and `safe` (`true` iff
`risk_tier == "trusted"`) — see [Consensus design](#consensus-design).

## Public contract interface

| Method | Type | Description |
|---|---|---|
| `analyze(url)` | write | Runs a new analysis and persists it (overwrites the previous one) |
| `get_report(url)` | view | Returns the latest full analysis (or `status="not_analyzed"`) |
| `is_safe(url)` | view | `true` / `false` |
| `get_trust_score(url)` | view | `0`-`100`, informational only — see below |
| `get_risk_tier(url)` | view | `"trusted"` \| `"caution"` \| `"high_risk"` — the consensus-bound decision bucket |
| `get_category(url)` | view | `Exchange` \| `Wallet` \| `DAO` \| `Protocol` \| `NFT` \| `Bridge` \| `Unknown` |
| `has_report(url)` | view | `true` if the URL has been analyzed at least once |
| `get_analyzed_urls()` | view | List of all analyzed URLs |
| `get_total_analyses()` | view | Total number of analyzed URLs |

Each report stores: URL, timestamp, requesting wallet, the 6 boolean
flags, `trust_score`, `risk_tier`, `category`, `reason` (free-form LLM
text), and `status`.

## Consensus design

Classifying "is this phishing?" is a subjective security judgment, not an
objective fact reproducible byte-for-byte, so the contract does **not**
use `strict_eq`. Instead:

- The **leader** downloads the page and calls the LLM.
- Each **validator** independently repeats the same process (fresh
  download + fresh LLM call) and compares:
  - The boolean flags (`phishing`, `malware`, `gambling`, `adult`,
    `official`) and `category` must **match exactly**.
  - `risk_tier` must **match exactly**. This is a discrete bucket
    (`trusted` / `caution` / `high_risk`) deterministically derived from
    `trust_score` and the phishing/malware flags. It's the actual
    consensus-bound decision surface: leader and validator must land in
    the *same bucket*, not merely within some numeric distance of each
    other. That guarantees two accepted results can never fall on
    opposite sides of a decision-relevant threshold.
  - `safe` is **not** requested from the LLM or compared directly — it's
    derived as `risk_tier == "trusted"`, so it's automatically consistent
    with `risk_tier` by construction (see below for why).
  - `trust_score` itself is **not** compared anymore and carries no
    tolerance — it's stored only for display. Two independent LLM runs
    that land in the same bucket (e.g. 72 and 95, both "trusted") reach
    consensus despite a 23-point gap, because that gap isn't
    decision-relevant. Two runs that land in different buckets (e.g. 68
    "caution" and 71 "trusted") fail consensus despite only a 3-point
    gap, because crossing that boundary is exactly the disagreement that
    matters.
  - `reason` is stored but **never compared** (it's free-form text; two
    LLMs phrase it differently even when they agree on the verdict).
- Errors are classified with deterministic prefixes (`[EXPECTED]`,
  `[EXTERNAL]`, `[TRANSIENT]`, `[LLM_ERROR]`) following GenLayer's
  recommended pattern for `run_nondet_unsafe`.

**Consumers should always branch on `risk_tier`, never on
`trust_score`.** Every integration example in this repo follows that
rule — see `examples/README.md`.

**Prompt precision is load-bearing for this design.** Exact-match
consensus only works if every LLM provider interprets `official` the
same way. An early version of the prompt left it under-defined for
non-Web3 sites (e.g. general websites, adult content), which caused
persistent consensus failures — different providers guessed differently
at whether "official" applies to a site that isn't a Web3 project. The
current prompt (`_build_prompt`) gives every requested field a precise,
provider-independent definition: `trust_score` is a pure security-risk
judgment decoupled from content type, and `official` defaults to false
for anything outside the fixed Web3 category list.

**Exact-match consensus also has to guard against a single response
contradicting itself, not just against leader and validator disagreeing
with each other.** `safe` is the clearest example, and went through two
rounds of fixes:

1. First fix: `safe` was taken directly from the LLM's own claim with no
   cross-check against `phishing`/`malware`. An LLM could report
   `safe: true` while also reporting `phishing: true`, and if leader and
   validator both happened to produce that same contradictory pair,
   consensus would accept it. Fixed by forcing `safe` to `false`
   whenever `phishing` or `malware` was `true`.
2. That closed only half the problem: with both flags `false`, an LLM
   could still pair `safe: true` with a low score (e.g. 20, stored as
   `risk_tier: "high_risk"`) or `safe: false` with a high score (e.g.
   80, stored as `risk_tier: "trusted"`) — either self-contradictory
   tuple still passed consensus if leader and validator both produced
   it. **`safe` is no longer requested from the LLM at all** (removed
   from the prompt's JSON schema) and is instead derived directly as
   `safe = (risk_tier == "trusted")`. That closes both directions of the
   contradiction by construction instead of guarding against only the
   phishing/malware-shaped half of it.

The same "derive, don't trust" pattern applies to two more fields:
- `official` → forced `false` whenever `category` is `"Unknown"` or
  `risk_tier != "trusted"` (which already implies `phishing`/`malware`
  are both `false`, by construction of `risk_tier`) — a phishing page,
  a low-trust site, or a non-Web3 site can't genuinely be "the official
  site."
- `trust_score` → clamped into the high-risk numeric range whenever
  `phishing` or `malware` is `true`, so the informational score can never
  visibly contradict the `risk_tier` badge shown next to it.

This doubles the verification cost (each node downloads and calls the LLM
twice: once as part of its own attempt and once when validating), but
that's the right price to pay for an anti-fraud reputation oracle: it
prioritizes consensus robustness over cost.

## Important note about `__init__` and storage

Storage fields (`TreeMap`, `DynArray`) are **not** initialized by hand.
The GenVM runner zero-initializes them automatically at deployment
(`TreeMap -> {}`, `DynArray -> []`). Trying to instantiate them manually,
e.g. `self.analyzed_urls = DynArray[str]()`, fails in production with:

```
TypeError: this class can't be instantiated by user
```

That's why this contract's `__init__` is empty (`pass`).

## Repository structure

```
contracts/
  url_reputation_oracle.py     # The Intelligent Contract
tests/
  direct/                      # Fast in-memory tests (mocked)
  integration/                 # Tests against GenLayer Studio / testnet
examples/                      # Integration by use case (see examples/README.md)
  shared/                       # TypeScript helpers (genlayer-js)
  shared_py/                    # Python helpers (genlayer-py)
  01-wallet-link-guard/          # Wallets: block links before opening them
  02-explorer-trust-badge/       # Explorers: trust badge
  03-nft-marketplace-collection-links/  # Marketplaces: validate collection links
  04-dao-governance-proposal-scanner/   # DAOs: scan proposal links
  05-launchpad-presale-guard/    # Launchpads: detect fraudulent presales
  06-defi-pool-url-screening/    # DeFi protocols: pool screening
gltest.config.yaml              # Network configuration for gltest
```

See [`examples/README.md`](./examples/README.md) for details on each use
case, with installation and run instructions.

## Local usage

### 1. Install tools

```bash
npm install -g genlayer
pip install genvm-linter
pip install "genlayer-test[sim]"
```

### 2. Lint

```bash
genvm-lint check contracts/url_reputation_oracle.py --json
```

### 3. Direct tests (fast, no Docker)

```bash
pytest tests/direct/ -v
```

`tests/direct/conftest.py` pins the GenVM SDK version used for these
tests to `v0.2.16` (the last release compatible with this contract's
pre-v0.3.0 API style). Without that pin, `genlayer-test`'s "latest"
auto-resolution can point at a newer GenVM release whose packaging no
longer matches what the installed `genlayer-test` version expects, which
fails every test before any of them run. Bump the pin only once this
contract itself migrates to the v0.3.0 API (see "Notes on the runner
version" below).

### 4. Run GenLayer Studio locally

```bash
genlayer init
genlayer up
```

Studio becomes available at `http://localhost:8080/`.

### 5. Integration tests (real consensus)

```bash
gltest tests/integration/ -v -s
```

### 6. Deploy and call

```bash
genlayer deploy --contract contracts/url_reputation_oracle.py
genlayer write <address> analyze --args '["https://uniswap.org"]'
genlayer call <address> get_report --args '["https://uniswap.org"]'
```

On **StudioNet** gas is zero (gasless), and that's expected. For
**Bradbury/Asimov** (real testnets) you need a funded account via the
[official faucet](https://testnet-faucet.genlayer.foundation/).

## Frontend/backend integration

The repo includes full integration examples in [`examples/`](./examples),
one for each use case described in the problem this oracle solves
(wallets, explorers, NFT marketplaces, DAOs, launchpads, DeFi protocols).
Summary:

- **Frontend/TypeScript**: use [`genlayer-js`](https://docs.genlayer.com/api-references/genlayer-js) (`createClient`, `readContract`, `writeContract`) against the schema generated by `genlayer schema <address>`. See `examples/shared/` for reusable helpers and `examples/01-wallet-link-guard`, `02-explorer-trust-badge`, `03-nft-marketplace-collection-links`, `05-launchpad-presale-guard`.
- **Backend/Python**: use `genlayer-py`, verifying the exact API in the SDK reference before writing code. See `examples/shared_py/` and `examples/04-dao-governance-proposal-scanner`, `06-defi-pool-url-screening`.

## Notes on the runner version

The `Depends` header pins the GenVM runner to a specific version
(`py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`), which
is the one used by all of GenLayer's current documentation (`from
genlayer import *`, `class X(gl.Contract)`, `@allow_storage`). There is a
published migration guide for a future v0.3.0 with a major standard
library restructuring (`import genlayer as gl`, `gl.contract.Contract`,
`gl.storage.allow`), but that version does not yet appear as a production
runner in the official changelog as of writing this contract. If you
migrate to v0.3.0 in the future, review the official migration guide
before updating the header.

## Possible future extensions

Out of scope for this MVP as described in the original spec, documented
here as a roadmap:

- Automatic periodic re-analysis and reputation updates.
- Change history (store every analysis, not just the latest).
- Analyzing a specific URL versus the whole domain.
- Impersonation detection by comparing against known brands.
- Integration with public phishing lists as additional evidence.
- Multi-language support in content analysis.
- Emitting events (`gl.vm.Event`) when a site's reputation changes.

## License

MIT — see [LICENSE](./LICENSE).

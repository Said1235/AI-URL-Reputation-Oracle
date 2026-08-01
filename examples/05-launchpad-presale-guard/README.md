# Use case: Launchpads — detect fraudulent presales

> From the original spec: *"Launchpads: detect potentially fraudulent
> presale pages."*

`presaleGuard.ts` maps the oracle's `risk_tier` directly to a launchpad
verdict:

| `risk_tier` | Verdict |
|---|---|
| `high_risk` | `rejected` (automatic) |
| `caution` | `manual_review` |
| `trusted` | `approved` (automatic) |

`risk_tier` is the field GenLayer's validator consensus is actually gated
on — leader and every validator had to independently agree on the exact
same bucket before the result was accepted on-chain. The verdict
deliberately does **not** apply its own cutoff to the numeric
`trust_score`: two equally-valid accepted reports for the same project
can carry different raw scores while still landing in the same tier, so
adding a second, ad hoc threshold on top of that number would reintroduce
the exact inconsistency the oracle's consensus design exists to prevent.
If you want a stricter or looser policy, that belongs in the oracle's own
tier breakpoints (`contracts/url_reputation_oracle.py`), not in this
integration.

## Usage

As a module, inside your submissions backend:

```ts
import { reviewPresaleSubmission } from "./presaleGuard";

const result = await reviewPresaleSubmission(project.website);
if (result.verdict === "rejected") {
  // return 400 to the project creator with result.reason
}
```

As a standalone CLI, for quick testing:

```bash
npm install
npx tsx presaleGuard.ts https://example-launch.xyz "Example Launch"
```

## Why a gray zone instead of just approve/reject

A launchpad handles real retail investor money — a false negative
(approving a fraudulent project) is far more costly than asking a human
moderator to review an ambiguous case. That's why `caution` maps to
`manual_review` instead of forcing an automatic binary decision.

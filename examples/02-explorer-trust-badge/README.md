# Use case: Blockchain explorers — trust badge

> From the original spec: *"Explorers: show a trust badge next to a
> contract's or project's URL."*

`TrustBadge.tsx` is a **read-only** React component: place it next to any
URL an explorer already shows (a verified contract's website link, the
site associated with a token's project, etc.) and it renders a color badge
based on the oracle's latest report.

## Why it's read-only

Unlike the wallet example (`01-wallet-link-guard`), this component
**never** automatically triggers `analyze()`. A public explorer renders
thousands of URLs per minute from indexed pages — if each one triggered an
on-chain transaction on first render, anyone could spend the explorer's
gas simply by visiting pages with new URLs.

Instead:
- If the URL was already analyzed (by another user, by an indexing job,
  etc.) the real badge is shown.
- If not, "Not analyzed" is shown in gray — neutral, doesn't penalize a
  project for not having a report yet.

If you want the explorer to also be able to **trigger** the first
analysis (e.g. with an "Analyze now" button visible only to moderators),
combine this component with `analyzeUrl` from
`examples/shared/oracleClient.ts` in a separate flow with its own access
control.

## Why the badge color comes from `risk_tier`, not `trust_score`

`classify()` maps the badge color directly from `report.risk_tier`
("trusted" / "caution" / "high_risk") instead of applying its own cutoff
to the numeric `trust_score`. `risk_tier` is the field GenLayer's
validator consensus is actually gated on — leader and every validator
had to independently agree on the exact same bucket. `trust_score` is
kept in the badge's tooltip/label purely for context; two equally-valid
accepted reports for the same site can carry different raw scores while
still agreeing on the tier, so building a second threshold on top of the
raw number here would reintroduce the inconsistency the oracle's
consensus design exists to prevent.

## Usage

```tsx
import { TrustBadge } from "./TrustBadge";

<div>
  <a href={project.website}>{project.website}</a>
  <TrustBadge url={project.website} />
</div>
```

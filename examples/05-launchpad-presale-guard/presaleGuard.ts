/**
 * Use case: LAUNCHPADS
 * -----------------------
 * "Launchpads: detect potentially fraudulent presale pages." (original
 * spec, Use cases section).
 *
 * Before approving a new presale project's listing, the launchpad runs
 * the project's declared URL against the oracle and automatically decides
 * between approving, rejecting, or sending it to manual review based on
 * the verdict.
 *
 * Usage as CLI:
 *   npx tsx presaleGuard.ts https://example-launch.xyz "Example Launch"
 */
import { createReadClient, createWriteClient } from "../shared/genlayerClient";
import { ensureAnalyzed } from "../shared/oracleClient";
import { CONTRACT_ADDRESS } from "../shared/config";

export type PresaleReviewResult =
  | { verdict: "approved"; trustScore: number }
  | { verdict: "rejected"; reason: string }
  | { verdict: "manual_review"; reason: string };

export async function reviewPresaleSubmission(projectUrl: string): Promise<PresaleReviewResult> {
  const readClient = createReadClient();
  const writeClient = createWriteClient();

  const report = await ensureAnalyzed(readClient, writeClient, CONTRACT_ADDRESS, projectUrl);

  // The verdict is a direct mapping from `risk_tier`, the one field
  // consensus is actually gated on (leader and every validator had to
  // land in the exact same bucket). `trust_score` is shown in the log
  // line for context only -- it must never itself decide the verdict,
  // since two equally-valid accepted analyses can carry different raw
  // scores while agreeing on the same tier.
  switch (report.risk_tier) {
    case "high_risk":
      return {
        verdict: "rejected",
        reason: `Flagged high_risk by the oracle: ${report.reason}`,
      };
    case "caution":
      return {
        verdict: "manual_review",
        reason: `Flagged caution by the oracle, requires human review: ${report.reason}`,
      };
    case "trusted":
      return { verdict: "approved", trustScore: report.trust_score };
    default:
      // Defensive fallback: TypeScript's UrlReport type guarantees
      // risk_tier is one of the three literals above, but an unexpected
      // on-chain value (e.g. a contract ABI mismatch) should fail loud
      // via manual review rather than silently returning `undefined`.
      return {
        verdict: "manual_review",
        reason: `Unrecognized risk_tier "${report.risk_tier}" returned by the oracle; treating as unverified.`,
      };
  }
}

/** Example usage inside a project submission endpoint. */
async function handleNewProjectSubmission(projectUrl: string, projectName: string) {
  console.log(`Reviewing submission for "${projectName}" (${projectUrl})...`);
  const result = await reviewPresaleSubmission(projectUrl);

  switch (result.verdict) {
    case "approved":
      console.log(`Automatically approved. Trust score: ${result.trustScore}/100.`);
      break;
    case "rejected":
      console.log(`Automatically rejected. Reason: ${result.reason}`);
      break;
    case "manual_review":
      console.log(`Sent to manual review. Reason: ${result.reason}`);
      break;
  }

  return result;
}

// Allows running this file directly as a CLI:
//   npx tsx presaleGuard.ts <url> [project_name]
const isDirectRun = process.argv[1]?.endsWith("presaleGuard.ts");
if (isDirectRun) {
  const [, , url, name] = process.argv;
  if (!url) {
    console.error("Usage: npx tsx presaleGuard.ts <url> [project_name]");
    process.exit(1);
  }
  handleNewProjectSubmission(url, name ?? "Unnamed project").catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

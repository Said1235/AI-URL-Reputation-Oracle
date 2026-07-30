/**
 * Use case: NFT MARKETPLACES
 * -----------------------------
 * "Marketplaces: validate NFT collection links." (original spec, Use
 * cases section).
 *
 * Moderation script: before approving or publishing a new collection on
 * the marketplace, the creator's declared website is run against the
 * oracle. Collections with phishing/malware are automatically rejected;
 * the rest are annotated with their trust score for review.
 *
 * Usage:
 *   npx tsx validateCollectionLinks.ts collections.json
 *
 * collections.json (example):
 *   [
 *     { "collectionId": "azuki", "website": "https://azuki.com" },
 *     { "collectionId": "fake-boredapes", "website": "https://claim-bayc-airdrop.xyz" }
 *   ]
 */
import { readFileSync, writeFileSync } from "node:fs";
import { createReadClient, createWriteClient } from "../shared/genlayerClient";
import { ensureAnalyzed } from "../shared/oracleClient";
import { CONTRACT_ADDRESS } from "../shared/config";

interface CollectionInput {
  collectionId: string;
  website: string;
}

interface CollectionResult extends CollectionInput {
  approved: boolean;
  trustScore: number;
  riskTier: "trusted" | "caution" | "high_risk";
  category: string;
  reason: string;
}

async function validateCollections(collections: CollectionInput[]): Promise<CollectionResult[]> {
  const readClient = createReadClient();
  const writeClient = createWriteClient();

  const results: CollectionResult[] = [];

  // Sequential on purpose: every analyze() without a prior report
  // triggers a transaction that waits for validator consensus. Running
  // them in parallel doesn't make them faster (still bound by the same
  // validator set) and complicates error handling.
  for (const collection of collections) {
    console.log(`Analyzing "${collection.collectionId}" -> ${collection.website}`);
    const report = await ensureAnalyzed(readClient, writeClient, CONTRACT_ADDRESS, collection.website);

    results.push({
      ...collection,
      // Approve only on `risk_tier === "trusted"`, the field consensus
      // actually gates on. Re-deriving approval from a hand-picked
      // combination of raw fields (e.g. `safe && !phishing && !malware`)
      // can diverge from the oracle's own verdict -- a site can be
      // `safe: true` with a mediocre trust_score that the oracle buckets
      // as "caution", and that divergence is exactly the inconsistency
      // this repo's consensus design was fixed to eliminate.
      approved: report.risk_tier === "trusted",
      trustScore: report.trust_score,
      riskTier: report.risk_tier,
      category: report.category,
      reason: report.reason,
    });
  }

  return results;
}

async function main() {
  const inputPath = process.argv[2];
  if (!inputPath) {
    console.error("Usage: npx tsx validateCollectionLinks.ts <collections.json>");
    process.exit(1);
  }

  const collections: CollectionInput[] = JSON.parse(readFileSync(inputPath, "utf-8"));
  const results = await validateCollections(collections);

  const rejected = results.filter((r) => !r.approved);
  console.log(`\n${results.length} collections analyzed, ${rejected.length} rejected.`);
  for (const r of rejected) {
    console.log(`  - ${r.collectionId}: ${r.reason} (trust_score=${r.trustScore})`);
  }

  const outputPath = "collection-validation-results.json";
  writeFileSync(outputPath, JSON.stringify(results, null, 2));
  console.log(`\nFull results saved to ${outputPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

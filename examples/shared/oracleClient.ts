/**
 * High-level wrapper over calls to the URLReputationOracle contract.
 * All use-case examples import these functions instead of calling
 * readContract/writeContract directly, so the field mapping isn't
 * repeated in every file.
 */
import { TransactionStatus, ExecutionResult } from "genlayer-js/types";

export interface UrlReport {
  url: string;
  timestamp: string;
  requester: string;
  safe: boolean;
  phishing: boolean;
  malware: boolean;
  gambling: boolean;
  adult: boolean;
  official: boolean;
  trust_score: number;
  risk_tier: "trusted" | "caution" | "high_risk";
  category: string;
  reason: string;
  status: "completed" | "not_analyzed";
}

// The SDK doesn't expose a simple public type for the client instance
// returned by createClient(); intentionally typed as `any` here.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type GenLayerClient = any;

export async function hasReport(
  readClient: GenLayerClient,
  contractAddress: `0x${string}`,
  url: string,
): Promise<boolean> {
  return (await readClient.readContract({
    address: contractAddress,
    functionName: "has_report",
    args: [url],
  })) as boolean;
}

export async function getReport(
  readClient: GenLayerClient,
  contractAddress: `0x${string}`,
  url: string,
): Promise<UrlReport> {
  return (await readClient.readContract({
    address: contractAddress,
    functionName: "get_report",
    args: [url],
  })) as UrlReport;
}

/**
 * Triggers analyze(url) and waits for the transaction to be ACCEPTED by
 * validator consensus. This can take several seconds (web fetch + LLM
 * call x2, once for the leader and once for each validator verifying it).
 */
export async function analyzeUrl(
  writeClient: GenLayerClient,
  contractAddress: `0x${string}`,
  url: string,
): Promise<`0x${string}`> {
  const txHash = await writeClient.writeContract({
    address: contractAddress,
    functionName: "analyze",
    args: [url],
    // `value` is a required field (bigint) in the installed SDK's real
    // writeContract signature, even though the docs describe it as
    // optional for calls that don't transfer GEN. 0n = no GEN sent.
    value: 0n,
  });

  const receipt = await writeClient.waitForTransactionReceipt({
    hash: txHash,
    status: TransactionStatus.ACCEPTED,
  });

  if (receipt.txExecutionResultName !== ExecutionResult.FINISHED_WITH_RETURN) {
    throw new Error(`analyze(${url}) failed on-chain: ${receipt.txExecutionResultName}`);
  }

  return txHash;
}

/**
 * Returns the report for `url`, analyzing it first if no report exists
 * yet. Note: if it triggers a new analysis, this call blocks until
 * consensus finishes. In an interactive UI, show a loading state
 * ("Analyzing link...") while it waits.
 */
export async function ensureAnalyzed(
  readClient: GenLayerClient,
  writeClient: GenLayerClient,
  contractAddress: `0x${string}`,
  url: string,
): Promise<UrlReport> {
  const alreadyAnalyzed = await hasReport(readClient, contractAddress, url);
  if (!alreadyAnalyzed) {
    await analyzeUrl(writeClient, contractAddress, url);
  }
  return getReport(readClient, contractAddress, url);
}

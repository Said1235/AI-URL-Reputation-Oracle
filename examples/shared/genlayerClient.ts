/**
 * genlayer-js client factories reused by all examples.
 *
 * API verified against the official GenLayerJS documentation
 * (createClient, createAccount, chains, readContract, writeContract,
 * waitForTransactionReceipt). No methods are invented: if you need
 * something not covered here, verify it at
 * https://docs.genlayer.com/api-references/genlayer-js before using it.
 */
import { createClient, createAccount } from "genlayer-js";
import { localnet, studionet, testnetAsimov, testnetBradbury } from "genlayer-js/chains";

import { GENLAYER_CHAIN } from "./config";

const CHAINS = { localnet, studionet, testnetAsimov, testnetBradbury } as const;

type ChainName = keyof typeof CHAINS;

function resolveChain(name: string = GENLAYER_CHAIN) {
  const chain = CHAINS[name as ChainName];
  if (!chain) {
    throw new Error(`Unknown network: "${name}". Options: ${Object.keys(CHAINS).join(", ")}`);
  }
  return chain;
}

/** Read-only client. Requires no account or signing. */
export function createReadClient(chainName?: string) {
  return createClient({ chain: resolveChain(chainName) });
}

/**
 * Write client for scripts/backends (not for a frontend with a user
 * wallet). By default it generates a fresh account on every call, which
 * is fine for testing but NOT for production: there you need to load a
 * persistent service account (e.g. a private key stored in a secret
 * manager) so you don't lose transaction history/funds between runs.
 *
 * For user-wallet flows (MetaMask, etc.) use the pattern described in
 * examples/01-wallet-link-guard/README.md instead of this function.
 */
export function createWriteClient(
  account: ReturnType<typeof createAccount> = createAccount(),
  chainName?: string,
) {
  return createClient({ chain: resolveChain(chainName), account });
}

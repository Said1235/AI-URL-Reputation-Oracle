/**
 * Shared configuration for all TypeScript examples.
 * Configure via environment variables (see .env.example) instead of
 * hardcoding the contract address here.
 */

export const CONTRACT_ADDRESS = (
  process.env.ORACLE_CONTRACT_ADDRESS ?? "0xYourDeployedContractAddressHere"
) as `0x${string}`;

/**
 * Network name confirmed in the genlayer-js SDK:
 * "localnet" | "studionet" | "testnetAsimov" | "testnetBradbury"
 */
export const GENLAYER_CHAIN = process.env.GENLAYER_CHAIN ?? "studionet";

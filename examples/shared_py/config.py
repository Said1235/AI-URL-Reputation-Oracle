"""
Shared configuration for the Python examples (DAO and DeFi). Configure via
environment variables instead of hardcoding the contract address.
"""

import os

CONTRACT_ADDRESS = os.environ.get(
    "ORACLE_CONTRACT_ADDRESS",
    "0xYourDeployedContractAddressHere",
)

# Supported networks (verified against the real genlayer-py package):
# "localnet" | "studionet" | "testnet_asimov" | "testnet_bradbury"
GENLAYER_CHAIN = os.environ.get("GENLAYER_CHAIN", "studionet")

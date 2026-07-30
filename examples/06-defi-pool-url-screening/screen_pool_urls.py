"""
Use case: DeFi PROTOCOLS
---------------------------
"DeFi protocols: automatically evaluate URLs associated with pools or
projects before showing them to users." (original spec, Use cases
section).

Periodic job (meant to run as a cron) that walks through a protocol's
active pools, analyzes the URL of the project associated with each one via
the oracle, and generates two files: one with pools safe to show in the
UI and another with pools flagged for review. The frontend consumes
"pools-displayable.json" (directly or via a cache/API layer) instead of
trusting unverified URLs.

Usage:
    python screen_pool_urls.py pools.json

pools.json (example):
    [
        {"poolId": "0xabc...", "projectUrl": "https://example-protocol.xyz"},
        {"poolId": "0xdef...", "projectUrl": "https://fake-yield-farm.xyz"}
    ]
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared_py.config import CONTRACT_ADDRESS, GENLAYER_CHAIN  # noqa: E402
from shared_py.oracle_client import (  # noqa: E402
    create_read_client,
    create_write_client,
    ensure_analyzed,
)


def screen_pools(pools: list[dict]) -> dict:
    read_client = create_read_client(GENLAYER_CHAIN)
    write_client = create_write_client(GENLAYER_CHAIN)

    displayable = []
    flagged = []

    for pool in pools:
        url = pool["projectUrl"]
        print(f"Analyzing pool {pool['poolId']} -> {url}")
        report = ensure_analyzed(read_client, write_client, CONTRACT_ADDRESS, url)

        entry = {
            **pool,
            "trustScore": report["trust_score"],
            "riskTier": report["risk_tier"],
            "category": report["category"],
            "reason": report["reason"],
        }

        # Only show pools bucketed as "trusted" -- the field GenLayer's
        # validator consensus is actually gated on. A hand-picked
        # combination like `safe and not phishing and not malware` can
        # let a mediocre-score pool through as "displayable" even when
        # the oracle itself buckets it as "caution".
        if report["risk_tier"] == "trusted":
            displayable.append(entry)
        else:
            flagged.append(entry)

    return {"displayable": displayable, "flagged": flagged}


def main():
    if len(sys.argv) < 2:
        print("Usage: python screen_pool_urls.py <pools.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        pools = json.load(f)

    result = screen_pools(pools)

    with open("pools-displayable.json", "w", encoding="utf-8") as f:
        json.dump(result["displayable"], f, indent=2)
    with open("pools-flagged.json", "w", encoding="utf-8") as f:
        json.dump(result["flagged"], f, indent=2)

    print(
        f"\n{len(result['displayable'])} pools safe to display, "
        f"{len(result['flagged'])} flagged for review."
    )
    print("Results in pools-displayable.json and pools-flagged.json")


if __name__ == "__main__":
    main()

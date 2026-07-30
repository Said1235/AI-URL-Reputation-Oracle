"""
Use case: DAOs
-----------------
"DAOs: verify links included in governance proposals." (original spec,
Use cases section).

Before a governance proposal is opened for voting, this script extracts
every URL from its text and runs it against the oracle. If any URL isn't
bucketed as "trusted" by the oracle's consensus-bound risk_tier, the
proposal is flagged for manual review instead of automatically opening
the vote. Meant to run as a bot/webhook when a new proposal is created,
or as a manual step before publishing it.

Usage:
    python scan_proposal_links.py proposal.txt

Exit code:
    0 -> all URLs passed the analysis
    2 -> some URLs are flagged, requires manual review
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared_py.config import CONTRACT_ADDRESS, GENLAYER_CHAIN  # noqa: E402
from shared_py.oracle_client import (  # noqa: E402
    create_read_client,
    create_write_client,
    ensure_analyzed,
)

URL_PATTERN = re.compile(r"https?://[^\s)\]\"']+")


def extract_urls(text: str) -> list[str]:
    """Extracts unique URLs from the proposal text, in the order they
    appear. Purely textual, no external dependencies."""
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_PATTERN.findall(text):
        cleaned = match.rstrip(".,;:!?)")
        if cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls


def scan_proposal(text: str) -> dict:
    read_client = create_read_client(GENLAYER_CHAIN)
    write_client = create_write_client(GENLAYER_CHAIN)

    urls = extract_urls(text)
    reports = []
    flagged = []

    for url in urls:
        print(f"Analyzing {url}...")
        report = ensure_analyzed(read_client, write_client, CONTRACT_ADDRESS, url)
        reports.append(report)
        # Flag anything that isn't "trusted" -- the field GenLayer's
        # validator consensus is actually gated on. A hand-picked
        # combination like `phishing or malware or not safe` can miss a
        # site that's `safe: true` with a mediocre trust_score the oracle
        # itself buckets as "caution", letting a questionable link slip
        # through unflagged.
        if report["risk_tier"] != "trusted":
            flagged.append(report)

    return {
        "total_urls": len(urls),
        "flagged_count": len(flagged),
        "requires_manual_review": len(flagged) > 0,
        "reports": reports,
        "flagged": flagged,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python scan_proposal_links.py <proposal_file.txt>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        proposal_text = f.read()

    result = scan_proposal(proposal_text)

    print(
        f"\n{result['total_urls']} URLs found, "
        f"{result['flagged_count']} flagged as risky."
    )

    if result["requires_manual_review"]:
        print("WARNING: this proposal requires manual review before opening the vote.")
        for report in result["flagged"]:
            print(f"  - {report['url']}: {report['reason']} (trust_score={report['trust_score']})")
        sys.exit(2)

    print("All URLs passed the reputation analysis.")
    sys.exit(0)


if __name__ == "__main__":
    main()

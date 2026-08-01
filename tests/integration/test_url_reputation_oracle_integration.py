"""
Integration test for URLReputationOracle against a running GenLayer
environment (GLSim, Studio local, or testnet).

Requires a running GenLayer environment (see README, "Local usage" section).

Run with:
    gltest tests/integration/ -v -s
"""

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def test_analyze_and_read_official_site():
    factory = get_contract_factory("URLReputationOracle")
    contract = factory.deploy(args=[])

    url = "https://uniswap.org"

    tx_receipt = contract.analyze(args=[url]).transact()
    assert tx_execution_succeeded(tx_receipt)

    report = contract.get_report(args=[url]).call()
    assert report["status"] == "completed"
    assert report["url"] == url
    assert 0 <= report["trust_score"] <= 100
    assert report["risk_tier"] in ("trusted", "caution", "high_risk")
    assert report["category"] in (
        "Exchange",
        "Wallet",
        "DAO",
        "Protocol",
        "NFT",
        "Bridge",
        "Unknown",
    )


def test_unanalyzed_url_returns_not_analyzed():
    factory = get_contract_factory("URLReputationOracle")
    contract = factory.deploy(args=[])

    report = contract.get_report(args=["https://never-analyzed-before.example"]).call()
    assert report["status"] == "not_analyzed"

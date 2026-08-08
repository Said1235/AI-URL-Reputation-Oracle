"""
Direct-mode tests for URLReputationOracle.

Run in-memory (no Docker, no real GenVM) using the `genlayer-test`
framework. Fast for iterating during development.

Run with:
    pytest tests/direct/ -v
"""

import json

CONTRACT_PATH = "contracts/url_reputation_oracle.py"

SAFE_HTML = """
<html><head><title>Uniswap</title></head>
<body><h1>Uniswap Protocol</h1><p>Official decentralized exchange.</p></body></html>
"""

PHISHING_HTML = """
<html><head><title>Claim your airdrop now!!!</title></head>
<body><h1>URGENT: Connect wallet to claim 1000 tokens</h1>
<form><input placeholder="Enter your seed phrase"></form></body></html>
"""

SAFE_LLM_RESPONSE = json.dumps(
    {
        "safe": True,
        "phishing": False,
        "malware": False,
        "gambling": False,
        "adult": False,
        "official": True,
        "trust_score": 94,
        "category": "Protocol",
        "reason": "Official protocol website",
    }
)

PHISHING_LLM_RESPONSE = json.dumps(
    {
        "safe": False,
        "phishing": True,
        "malware": False,
        "gambling": False,
        "adult": False,
        "official": False,
        "trust_score": 3,
        "category": "Unknown",
        "reason": "Seed phrase phishing form detected",
    }
)


def _mock_happy_path(direct_vm, url: str, llm_response: str, html: str):
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": html})
    direct_vm.mock_llm(r".*", llm_response)


def test_analyze_safe_url(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://uniswap.org"
    _mock_happy_path(direct_vm, url, SAFE_LLM_RESPONSE, SAFE_HTML)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["status"] == "completed"
    assert report["safe"] is True
    assert report["phishing"] is False
    assert report["official"] is True
    assert report["trust_score"] == 94
    assert report["risk_tier"] == "trusted"
    assert report["category"] == "Protocol"
    assert report["url"] == url


def test_analyze_phishing_url(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://claim-airdrop.xyz"
    _mock_happy_path(direct_vm, url, PHISHING_LLM_RESPONSE, PHISHING_HTML)

    contract.analyze(url)

    assert contract.is_safe(url) is False
    assert contract.get_trust_score(url) == 3
    assert contract.get_risk_tier(url) == "high_risk"
    assert contract.get_category(url) == "Unknown"


def test_safe_is_forced_false_when_llm_contradicts_itself(direct_vm, direct_deploy, direct_alice):
    """Regression test: an LLM can report safe=true while ALSO reporting
    phishing=true (or malware=true) -- a self-contradictory response. The
    contract must never store that contradiction: safe must be forced to
    false whenever phishing or malware is true, regardless of what the
    LLM's own "safe" field claimed. Without this, is_safe(url) could
    return true for a URL that risk_tier correctly buckets as
    high_risk."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://claim-airdrop.xyz"
    contradictory_response = json.dumps(
        {
            "safe": True,  # contradicts phishing=True below
            "phishing": True,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": False,
            "trust_score": 5,
            "category": "Unknown",
            "reason": "Seed phrase phishing form detected",
        }
    )
    _mock_happy_path(direct_vm, url, contradictory_response, PHISHING_HTML)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["phishing"] is True
    assert report["safe"] is False  # forced false despite the LLM's raw safe=true claim
    assert report["risk_tier"] == "high_risk"
    assert contract.is_safe(url) is False


def test_official_is_forced_false_when_category_is_unknown(direct_vm, direct_deploy, direct_alice):
    """Regression test for the same class of bug: an LLM can report
    official=true while ALSO reporting category="Unknown" -- but
    "official" is only meaningful for a real Web3/crypto category per the
    prompt's own definition, so that combination is self-contradictory.
    official must be forced to false whenever category is "Unknown",
    regardless of what the LLM's own "official" field claimed."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://example-generic-site.com"
    html = "<html><body>Generic site</body></html>"
    contradictory_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,  # contradicts category="Unknown" below
            "trust_score": 80,
            "category": "Unknown",
            "reason": "Well-established generic site",
        }
    )
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": html})
    direct_vm.mock_llm(r".*", contradictory_response)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["category"] == "Unknown"
    assert report["official"] is False  # forced false despite the LLM's raw official=true claim


def test_official_is_forced_false_when_phishing_is_true(direct_vm, direct_deploy, direct_alice):
    """Regression test for the same class of bug, third pairing: an LLM
    can report official=true (with a real Web3 category) while ALSO
    reporting phishing=true -- but a phishing page is by definition
    impersonating something else, so it cannot genuinely be the official
    site. official must be forced to false whenever phishing or malware
    is true, regardless of category or the LLM's own "official" claim."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://fake-uniswap-clone.xyz"
    html = "<html><body>Connect wallet to claim rewards</body></html>"
    contradictory_response = json.dumps(
        {
            "safe": False,
            "phishing": True,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,  # contradicts phishing=True and a real category
            "trust_score": 10,
            "category": "Protocol",
            "reason": "Impersonates Uniswap with a fake claim-rewards form",
        }
    )
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": html})
    direct_vm.mock_llm(r".*", contradictory_response)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["phishing"] is True
    assert report["official"] is False  # forced false despite the LLM's raw official=true claim


def test_official_is_forced_false_when_score_is_low_with_no_threat_flags(direct_vm, direct_deploy, direct_alice):
    """Regression test for the strengthened official guard: an LLM can
    report official=true (with a real Web3 category) alongside a low
    trust_score even when phishing and malware are both false. Since the
    prompt's own trust_score definition ties a low score to deceptive or
    scam-like behavior, official=true paired with risk_tier != "trusted"
    is just as self-contradictory as official=true + phishing=true.
    official is now tied directly to risk_tier == "trusted", which
    subsumes the phishing/malware check and closes this gap too."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://sketchy-protocol.example"
    html = "<html><body>Some protocol site</body></html>"
    contradictory_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,  # contradicts a score low enough to bucket as high_risk
            "trust_score": 15,
            "category": "Protocol",
            "reason": "Claims to be official but largely nonfunctional",
        }
    )
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": html})
    direct_vm.mock_llm(r".*", contradictory_response)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["risk_tier"] == "high_risk"
    assert report["official"] is False  # forced false despite the LLM's raw official=true claim


def test_trust_score_is_clamped_when_phishing_or_malware_is_true(direct_vm, direct_deploy, direct_alice):
    """Regression test closing the last gap in the same class of bug:
    trust_score is informational only and never gates consensus, but an
    LLM could still pair phishing=true with a high trust_score like 90 --
    harmless for decisions (every consumer reads risk_tier, never
    trust_score), but a visibly self-contradictory number next to a
    "high_risk" label for anyone glancing at the stored report. High
    threat-flag scores must be clamped into the high_risk numeric range."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://claim-airdrop.xyz"
    contradictory_response = json.dumps(
        {
            "safe": False,
            "phishing": True,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": False,
            "trust_score": 90,  # contradicts phishing=True
            "category": "Unknown",
            "reason": "Seed phrase phishing form detected",
        }
    )
    _mock_happy_path(direct_vm, url, contradictory_response, PHISHING_HTML)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["phishing"] is True
    assert report["trust_score"] <= 29  # clamped into the high_risk range
    assert report["risk_tier"] == "high_risk"


def test_safe_true_with_low_score_and_no_threat_flags_is_forced_false(direct_vm, direct_deploy, direct_alice):
    """Regression test for the exact scenario from the rejection: an LLM
    can report safe=true with a low trust_score (e.g. 20) even when
    phishing and malware are BOTH false -- the earlier fix only forced
    safe=false when phishing/malware was true, leaving this half of the
    contradiction open. A score of 20 buckets as risk_tier="high_risk";
    safe must match that, not the LLM's independent safe=true claim."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://mediocre-but-not-flagged.example"
    html = "<html><body>Some barely-functional site</body></html>"
    contradictory_response = json.dumps(
        {
            "safe": True,  # contradicts a score low enough to bucket as high_risk
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": False,
            "trust_score": 20,
            "category": "Unknown",
            "reason": "Poorly maintained but no active threat detected",
        }
    )
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": html})
    direct_vm.mock_llm(r".*", contradictory_response)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["phishing"] is False
    assert report["malware"] is False
    assert report["risk_tier"] == "high_risk"
    assert report["safe"] is False  # derived from risk_tier, not the LLM's raw safe=true claim
    assert contract.is_safe(url) is False


def test_safe_false_with_high_score_and_no_threat_flags_is_forced_true(direct_vm, direct_deploy, direct_alice):
    """Mirror of the previous test, the other direction from the same
    rejection: an LLM can report safe=false with a high trust_score (e.g.
    80) even when phishing and malware are both false. A score of 80
    buckets as risk_tier="trusted"; safe must match that, not the LLM's
    independent safe=false claim."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://uniswap.org"
    contradictory_response = json.dumps(
        {
            "safe": False,  # contradicts a score high enough to bucket as trusted
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,
            "trust_score": 80,
            "category": "Protocol",
            "reason": "Looks legitimate overall",
        }
    )
    _mock_happy_path(direct_vm, url, contradictory_response, SAFE_HTML)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["phishing"] is False
    assert report["malware"] is False
    assert report["risk_tier"] == "trusted"
    assert report["safe"] is True  # derived from risk_tier, not the LLM's raw safe=false claim
    assert contract.is_safe(url) is True


def test_get_report_before_analysis_is_not_analyzed(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT_PATH)

    report = contract.get_report("https://never-checked.com")
    assert report["status"] == "not_analyzed"
    assert report["trust_score"] == 0
    # Fail-safe default: an unanalyzed URL must never be treated as
    # trusted by a consumer keying off risk_tier.
    assert report["risk_tier"] == "high_risk"


def test_is_safe_before_analysis_reverts(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT_PATH)

    with direct_vm.expect_revert("has not been analyzed"):
        contract.is_safe("https://never-checked.com")


def test_invalid_url_reverts(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    with direct_vm.expect_revert("Invalid URL"):
        contract.analyze("not-a-url")


def test_reanalysis_overwrites_and_does_not_duplicate(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://uniswap.org"
    _mock_happy_path(direct_vm, url, SAFE_LLM_RESPONSE, SAFE_HTML)
    contract.analyze(url)
    assert contract.get_total_analyses() == 1

    # Re-analyze the same URL: the score changes but it must not be
    # duplicated in the list of analyzed URLs.
    updated_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,
            "trust_score": 88,
            "category": "Protocol",
            "reason": "Still official, minor content change",
        }
    )
    direct_vm.clear_mocks()
    _mock_happy_path(direct_vm, url, updated_response, SAFE_HTML)
    contract.analyze(url)

    assert contract.get_total_analyses() == 1
    assert contract.get_trust_score(url) == 88
    assert contract.get_risk_tier(url) == "trusted"


def test_url_normalization_is_case_insensitive_on_host(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    # The contract lowercases the host in `_normalize_url()` *before* the
    # actual `gl.nondet.web.render()` call, so the mock must be registered
    # against the normalized (lowercase) URL even though `analyze()` below
    # is called with a mixed-case one -- that's the whole point of this
    # test: verifying the mixed-case input still resolves correctly.
    _mock_happy_path(direct_vm, "https://uniswap.org", SAFE_LLM_RESPONSE, SAFE_HTML)
    contract.analyze("https://Uniswap.org")

    # Same URL with different host casing must resolve to the same report.
    assert contract.is_safe("https://uniswap.org/") is True


def test_validator_disagrees_on_conflicting_llm_output(direct_vm, direct_deploy, direct_alice):
    """If the validator gets a verdict opposite to the leader's (e.g. a
    different LLM hallucinates differently), consensus should reject the
    result instead of blindly accepting it."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://uniswap.org"
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": SAFE_HTML})
    direct_vm.mock_llm(r".*", SAFE_LLM_RESPONSE)

    # Runs leader_fn and captures the leader's result.
    contract.analyze(url)

    # Now simulate the validator, when independently re-running, getting an
    # opposite verdict (safe=False instead of True).
    direct_vm.clear_mocks()
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": SAFE_HTML})
    direct_vm.mock_llm(r".*", PHISHING_LLM_RESPONSE)

    assert direct_vm.run_validator() is False


def test_validator_agrees_within_same_risk_tier_despite_score_gap(direct_vm, direct_deploy, direct_alice):
    """Regression test for the rejected consensus design: two independent
    LLM runs that land in the SAME risk tier must reach consensus even if
    their raw trust_score values are far apart, because that disagreement
    is not decision-relevant. Leader=72 and validator=95 are both
    "trusted" (> RISK_TIER_CAUTION_MAX=69), a 23-point raw gap that would
    have failed the old +-10 numeric-tolerance rule."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://uniswap.org"
    leader_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,
            "trust_score": 72,
            "category": "Protocol",
            "reason": "Looks official",
        }
    )
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": SAFE_HTML})
    direct_vm.mock_llm(r".*", leader_response)
    contract.analyze(url)
    assert contract.get_risk_tier(url) == "trusted"

    validator_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,
            "trust_score": 95,
            "category": "Protocol",
            "reason": "Clearly the official site",
        }
    )
    direct_vm.clear_mocks()
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": SAFE_HTML})
    direct_vm.mock_llm(r".*", validator_response)

    assert direct_vm.run_validator() is True


def test_validator_disagrees_across_risk_tier_boundary_despite_small_score_gap(
    direct_vm, direct_deploy, direct_alice
):
    """Core fix for the rejected consensus design: two independent LLM
    runs that land in DIFFERENT risk tiers must fail consensus even if
    their raw trust_score values are close, because crossing a
    decision-relevant boundary is exactly the disagreement that matters.
    Leader=71 ("trusted") and validator=68 ("caution") are only 3 points
    apart -- close enough that the old +-10 numeric-tolerance rule would
    have wrongly accepted this as agreement, even though it straddles the
    caution/trusted boundary that downstream consumers key off of."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://uniswap.org"
    leader_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,
            "trust_score": 71,
            "category": "Protocol",
            "reason": "Looks official",
        }
    )
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": SAFE_HTML})
    direct_vm.mock_llm(r".*", leader_response)
    contract.analyze(url)
    assert contract.get_risk_tier(url) == "trusted"

    validator_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": False,
            "official": True,
            "trust_score": 68,
            "category": "Protocol",
            "reason": "Mostly looks official, minor concerns",
        }
    )
    direct_vm.clear_mocks()
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": SAFE_HTML})
    direct_vm.mock_llm(r".*", validator_response)

    assert direct_vm.run_validator() is False


def test_non_web3_site_with_consistent_llm_answers_reaches_consensus(direct_vm, direct_deploy, direct_alice):
    """Regression test for a live consensus failure observed on a
    non-Web3 site (a large, legitimate adult-content site with no
    phishing/malware). Before `_build_prompt` defined `safe`/`official`
    precisely, different LLM providers guessed inconsistently at what
    those fields mean for a site outside the Web3 category, causing
    persistent MAJORITY_DISAGREE results.

    This test documents the CORRECT, consistent answer under the fixed
    prompt semantics: `official` is false by default for non-Web3 sites,
    `safe`/`trust_score` reflect security risk only (not content type),
    and two independent LLM calls that both follow that definition reach
    consensus even though the site is adult content and category=Unknown.
    It doesn't test the LLM itself (the call is mocked), only that the
    contract correctly accepts and buckets this input once the providers
    agree."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice

    url = "https://example-adult-site.com"
    html = """
    <html><head><title>Example Site</title></head>
    <body><h1>Example Content</h1></body></html>
    """
    consistent_response = json.dumps(
        {
            "safe": True,
            "phishing": False,
            "malware": False,
            "gambling": False,
            "adult": True,
            "official": False,
            "trust_score": 85,
            "category": "Unknown",
            "reason": "Large established site, no phishing or malware indicators",
        }
    )
    direct_vm.mock_web(url.replace(".", r"\.").replace("/", r"\/"), {"status": 200, "body": html})
    direct_vm.mock_llm(r".*", consistent_response)

    contract.analyze(url)

    report = contract.get_report(url)
    assert report["safe"] is True
    assert report["adult"] is True
    assert report["official"] is False
    assert report["category"] == "Unknown"
    assert report["risk_tier"] == "trusted"

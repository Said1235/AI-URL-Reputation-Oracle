# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
AI URL Reputation Oracle
========================

Decentralized URL reputation oracle for GenLayer.

Instead of relying on a centralized blacklist, this contract uses
GenLayer's non-deterministic web access (`gl.nondet.web.render`) to fetch
a page's real HTML, asks an LLM to classify it as structured JSON, and
uses GenLayer's validator consensus (Optimistic Democracy) to agree on the
result before storing it on-chain.

Public interface:
    - analyze(url)          -> runs a new analysis and persists it
    - get_report(url)       -> latest full analysis for a URL
    - is_safe(url)          -> bool
    - get_trust_score(url)  -> 0-100 (informational, see Consensus design)
    - get_risk_tier(url)    -> "trusted" | "caution" | "high_risk" (consensus-bound decision bucket)
    - get_category(url)     -> Exchange | Wallet | DAO | Protocol | NFT | Bridge | Unknown
    - has_report(url)       -> bool, whether url has ever been analyzed
    - get_analyzed_urls()   -> list of analyzed URLs (enumeration)
    - get_total_analyses()  -> total number of analyzed URLs

Consensus design
-----------------
Classifying "is this phishing/malware/safe" is a security judgment, not an
objective fact every node can reproduce byte-for-byte. That's why this
contract does NOT use `strict_eq`. Instead, each validator independently
re-runs `leader_fn` (a fresh download + a fresh LLM call) and compares:
    - The boolean decision fields (safe, phishing, malware, gambling,
      adult, official) must match exactly.
    - `category` must match exactly (already normalized to a fixed enum).
    - `risk_tier` must match exactly. This is a discrete bucket
      ("trusted" / "caution" / "high_risk") deterministically derived from
      `trust_score` and the phishing/malware flags (see
      `_compute_risk_tier`). It is the actual consensus-bound decision
      surface: two LLM runs must land in the SAME bucket, not merely
      within some numeric distance of each other, for consensus to
      accept a result. This guarantees that any two accepted results can
      never land on opposite sides of a decision-relevant threshold,
      because reaching consensus already required independent agreement
      on which side of every bucket boundary the site falls.
    - `trust_score` itself is stored for display purposes only and is
      NOT part of the consensus gate anymore. Two independent LLM calls
      landing in the same bucket (e.g. 72 and 95, both "trusted") is
      accepted even though the raw numbers differ a lot, precisely
      because that disagreement is not decision-relevant. Conversely, two
      calls landing in different buckets (e.g. 68 "caution" and 71
      "trusted") are rejected even though the raw numbers are close,
      because that disagreement IS decision-relevant.
    - `reason` is stored but NEVER compared (it's free-form text).
This follows the "Partial Field Matching" pattern recommended for
classification/security tasks on GenLayer, with the numeric-tolerance
comparison replaced by an exact-match discrete bucket so downstream
consumers get a single authoritative decision signal instead of having to
apply their own threshold to a continuous, tolerance-bound number.

Prompt precision is load-bearing for this design. Exact-match consensus
on `safe`/`official`/`risk_tier` only reaches agreement if every LLM
provider interprets those fields the same way. An early version of
`_build_prompt` defined `official` only in terms of Web3 projects and
never defined `safe` at all, which was fine for on-topic URLs but caused
persistent MAJORITY_DISAGREE / UNDETERMINED results for ordinary
non-Web3 sites (e.g. a large adult-content site with no phishing or
malware): different providers guessed differently at whether "official"
or "safe" applies to something outside the Web3 category, and a
borderline `trust_score` near a tier boundary (e.g. 29 vs 30) made it
worse. The current prompt fixes this by giving every field a precise,
provider-independent definition -- notably, "safe" and "trust_score" are
defined as pure security/scam-risk judgments, decoupled from content
type or Web3-relevance, and "official" is explicitly false by default
for anything outside the fixed Web3 category list.
"""

import json
import re
import typing
from dataclasses import dataclass

from genlayer import *

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Deterministic error prefixes, used to classify failures inside the
# validator_fn of run_nondet_unsafe (pattern recommended by GenLayer).
ERROR_EXPECTED = "[EXPECTED]"      # Business-logic error (invalid input, etc.)
ERROR_EXTERNAL = "[EXTERNAL]"      # The URL responded but with a problem (e.g. empty)
ERROR_TRANSIENT = "[TRANSIENT]"    # Temporary network failure (timeout, DNS, 5xx)
ERROR_LLM = "[LLM_ERROR]"          # The LLM returned something unusable

# Fixed categories, kept to favor consensus among validators (see spec).
ALLOWED_CATEGORIES = ("Exchange", "Wallet", "DAO", "Protocol", "NFT", "Bridge", "Unknown")

# Fixed, deterministic breakpoints used by `_compute_risk_tier` to bucket
# a continuous trust_score into a discrete decision surface. These
# replace the old raw +-10 numeric tolerance: what must now match exactly
# between leader and validator is *which bucket* the score falls into,
# not the score itself.
#   score <  RISK_TIER_HIGH_RISK_MAX + 1        -> "high_risk"
#   RISK_TIER_HIGH_RISK_MAX < score <= RISK_TIER_CAUTION_MAX -> "caution"
#   score > RISK_TIER_CAUTION_MAX                -> "trusted"
RISK_TIER_HIGH_RISK_MAX = 29
RISK_TIER_CAUTION_MAX = 69

# Character limit for HTML sent to the LLM (avoids giant prompts).
MAX_CONTENT_CHARS = 12_000

# Character limit for the "reason" field stored on-chain.
MAX_REASON_CHARS = 280


# ---------------------------------------------------------------------------
# Persistent storage type
# ---------------------------------------------------------------------------

@allow_storage
@dataclass
class Report:
    url: str
    timestamp: str          # ISO 8601, taken from gl.message_raw['datetime']
    requester: Address       # wallet that requested the analysis
    safe: bool
    phishing: bool
    malware: bool
    gambling: bool
    adult: bool
    official: bool
    trust_score: u8          # 0-100, informational only (see Consensus design)
    risk_tier: str            # "trusted" | "caution" | "high_risk" -- the consensus-bound decision bucket
    category: str
    reason: str
    status: str              # "completed" once stored


# ---------------------------------------------------------------------------
# Deterministic helpers (no non-deterministic calls inside)
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Normalizes a URL for use as a storage key.

    Purely deterministic: only string manipulation, no network or external
    dependencies, so it produces the same result on every node. Returns ""
    if the URL doesn't have a valid http(s) scheme.
    """
    trimmed = url.strip()
    if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
        return ""

    scheme_end = trimmed.index("://") + 3
    scheme = trimmed[:scheme_end].lower()
    rest = trimmed[scheme_end:]

    if len(rest) == 0:
        return ""

    slash_index = rest.find("/")
    if slash_index == -1:
        host, path = rest, ""
    else:
        host, path = rest[:slash_index], rest[slash_index:]

    host = host.lower()
    if path == "/":
        path = ""

    return scheme + host + path


def _normalize_category(raw_category: str) -> str:
    """Maps the category returned by the LLM to one of the fixed enum
    values. Done on both sides (leader and validator) before comparing, so
    two equivalent responses ("exchange" vs "Exchange") don't cause a
    spurious disagreement."""
    lowered = raw_category.strip().lower()
    for canonical in ALLOWED_CATEGORIES:
        if canonical.lower() == lowered:
            return canonical
    return "Unknown"


def _build_prompt(url: str, content: str) -> str:
    return f"""You are a Web3 security analyst reviewing a website for a
decentralized reputation oracle. Other smart contracts and wallets will rely
on your verdict before letting users interact with this URL. Multiple
independent reviewers analyze the same page and must reach the SAME
conclusions, so follow the field definitions below exactly instead of your
own judgment call -- consistency matters more than nuance here.

URL being analyzed:
{url}

Raw HTML content of the page (may be truncated):
---
{content}
---

Field definitions (follow exactly):

- "phishing": true only if the page impersonates a brand, uses a fake
  login/connect-wallet form to steal credentials or funds, or otherwise
  tries to deceive the visitor into giving up sensitive information.
- "malware": true only if the page distributes malicious software or
  contains obfuscated/injected scripts designed to compromise the visitor.
- "gambling": true if the page's primary purpose is gambling/betting.
- "adult": true if the page's primary content is sexually explicit.
- "official": ONLY meaningful when the page represents a specific
  Web3/crypto project (an exchange, wallet, DAO, protocol, NFT collection,
  or bridge). Set it to true only if this looks like that project's
  genuine, official site. If the page is not about a Web3/crypto project
  at all -- general websites, adult sites, gambling sites, news, blogs,
  etc. -- ALWAYS set "official" to false; the concept does not apply to it.
- "safe": a SECURITY judgment ONLY -- true unless the page shows phishing,
  malware, or scam-like deception as defined above. Do NOT base "safe" on
  content type, legality, or how "wholesome" the site is: a legal site
  with no security threat is "safe": true even if it is gambling or adult
  content, since that's already captured separately by the
  "gambling"/"adult" flags.
- "trust_score": 0-100, a SECURITY-RISK score using the SAME standard as
  "safe" above. A well-established, non-malicious site should score high
  (70-100) regardless of its topic or whether it's related to Web3. Only
  lower the score for concrete signs of risk: phishing, malware, deceptive
  practices, or scam-like behavior. Do NOT lower the score merely because
  the site is unrelated to Web3, or merely because it is adult or
  gambling content.
- "category": one of "Exchange", "Wallet", "DAO", "Protocol", "NFT",
  "Bridge" if the page clearly represents that kind of Web3/crypto
  project, otherwise "Unknown".
- "reason": short one-sentence justification (max 200 characters).

Respond ONLY with a single JSON object, no markdown fences, no extra text,
matching exactly this schema:
{{
    "safe": true or false,
    "phishing": true or false,
    "malware": true or false,
    "gambling": true or false,
    "adult": true or false,
    "official": true or false,
    "trust_score": integer from 0 to 100,
    "category": one of "Exchange", "Wallet", "DAO", "Protocol", "NFT", "Bridge", "Unknown",
    "reason": short one-sentence justification (max 200 characters)
}}"""


def _clean_llm_json(text: str) -> dict:
    """Extracts and cleans a JSON object from the LLM's raw text (sometimes
    wrapped in markdown fences or with trailing commas)."""
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1:
        raise gl.vm.UserError(f"{ERROR_LLM} No JSON object found in LLM response")
    snippet = text[first : last + 1]
    snippet = re.sub(r",(?!\s*?[\{\[\"'\w])", "", snippet)  # strip trailing commas
    try:
        return json.loads(snippet)
    except json.JSONDecodeError as e:
        raise gl.vm.UserError(f"{ERROR_LLM} Could not parse LLM JSON: {e}")


def _as_bool(raw: dict, key: str) -> bool:
    value = raw.get(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def _compute_risk_tier(data: dict) -> str:
    """Deterministically derives a discrete, exact-match risk tier from
    the LLM's normalized output. Unlike the raw 0-100 trust_score (which
    naturally varies run to run since it's an LLM's subjective number),
    this tier is what consensus is actually gated on for score-driven
    decisions: leader and validator must land in the SAME tier, not
    merely within some numeric distance of each other.

    phishing/malware always force "high_risk" regardless of the numeric
    score, since those flags are already exact-matched independently and
    should dominate the bucket.
    """
    if data.get("phishing") or data.get("malware"):
        return "high_risk"

    score = data.get("trust_score", 0)
    if score <= RISK_TIER_HIGH_RISK_MAX:
        return "high_risk"
    if score <= RISK_TIER_CAUTION_MAX:
        return "caution"
    return "trusted"


def _parse_and_normalize(raw: typing.Any) -> dict:
    """Defensive parsing of the LLM response: handles raw text, wrong-typed
    values, name aliases, and coerces everything to the contract's fixed
    schema."""
    if isinstance(raw, str):
        raw = _clean_llm_json(raw)
    if not isinstance(raw, dict):
        raise gl.vm.UserError(f"{ERROR_LLM} LLM response is not a JSON object")

    raw_score = raw.get("trust_score", raw.get("score", 0))
    try:
        trust_score = int(round(float(raw_score)))
    except (TypeError, ValueError):
        raise gl.vm.UserError(f"{ERROR_LLM} Non-numeric trust_score in LLM response")
    trust_score = max(0, min(100, trust_score))

    category = _normalize_category(str(raw.get("category", "Unknown")))
    reason = str(raw.get("reason", "")).strip()[:MAX_REASON_CHARS]

    result = {
        "safe": _as_bool(raw, "safe"),
        "phishing": _as_bool(raw, "phishing"),
        "malware": _as_bool(raw, "malware"),
        "gambling": _as_bool(raw, "gambling"),
        "adult": _as_bool(raw, "adult"),
        "official": _as_bool(raw, "official"),
        "trust_score": trust_score,
        "category": category,
        "reason": reason,
    }
    result["risk_tier"] = _compute_risk_tier(result)
    return result


def _compare_analysis(leader_data: dict, validator_data: dict) -> bool:
    """Compares only the decision fields. `reason` is free-form text and is
    never compared (see Pattern 1: Partial Field Matching).

    `risk_tier` is compared with an EXACT match, same as the boolean
    flags and `category`. This is the hard consensus gate for the
    numeric trust_score: the raw score is no longer compared with a
    tolerance window, because any nonzero tolerance can straddle some
    consumer's decision threshold. Requiring exact agreement on the
    bucket instead means an accepted result always reflects independent
    agreement on which side of every relevant boundary the site falls.
    """
    decision_fields = ("safe", "phishing", "malware", "gambling", "adult", "official", "category", "risk_tier")
    for field in decision_fields:
        if leader_data.get(field) != validator_data.get(field):
            return False

    return True


def _handle_leader_error(leaders_res: typing.Any, leader_fn) -> bool:
    """Re-runs leader_fn on the validator and compares the error type to
    decide whether it's an expected disagreement or not. Follows the error
    classification pattern recommended by GenLayer."""
    leader_msg = getattr(leaders_res, "message", str(leaders_res))
    try:
        leader_fn()
        return False  # leader failed but validator succeeded -> disagreement
    except gl.vm.UserError as e:
        validator_msg = getattr(e, "message", str(e))
        if validator_msg.startswith(ERROR_EXPECTED) or validator_msg.startswith(ERROR_EXTERNAL):
            return validator_msg == leader_msg
        if validator_msg.startswith(ERROR_TRANSIENT) and leader_msg.startswith(ERROR_TRANSIENT):
            return True
        # LLM or unknown errors: disagreement, force leader rotation
        return False
    except Exception:
        return False


def _fetch_page_content(url: str) -> str:
    """Downloads the page's HTML. MUST be called from inside
    leader_fn/validator_fn (inside a non-deterministic block)."""
    try:
        content = gl.nondet.web.render(url, mode="html")
    except Exception as e:
        raise gl.vm.UserError(f"{ERROR_TRANSIENT} Failed to fetch URL content: {e}")

    if not content:
        raise gl.vm.UserError(f"{ERROR_EXTERNAL} Empty response from URL")

    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS]

    return content


def _call_llm_analysis(url: str, content: str) -> dict:
    """Asks the LLM for the verdict as JSON and normalizes it. MUST be
    called from inside leader_fn/validator_fn."""
    prompt = _build_prompt(url, content)
    try:
        raw = gl.nondet.exec_prompt(prompt, response_format="json")
    except Exception as e:
        raise gl.vm.UserError(f"{ERROR_LLM} LLM call failed: {e}")
    return _parse_and_normalize(raw)


def _run_analysis(url: str) -> dict:
    """Full non-deterministic analysis body: download + LLM."""
    content = _fetch_page_content(url)
    return _call_llm_analysis(url, content)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class URLReputationOracle(gl.Contract):
    reports: TreeMap[str, Report]
    analyzed_urls: DynArray[str]

    def __init__(self):
        # `reports` and `analyzed_urls` don't need to be initialized by
        # hand: storage fields (TreeMap/DynArray) are automatically
        # zero-initialized ({} and [] respectively) at contract deployment.
        # Manually instantiating storage generics (e.g. `DynArray[str]()`)
        # fails on the GenVM runner with
        # "TypeError: this class can't be instantiated by user".
        pass

    # -- Writes ---------------------------------------------------------

    @gl.public.write
    def analyze(self, url: str) -> None:
        """Runs a new reputation analysis for `url` and persists it.
        Overwrites any previous analysis of the same URL."""
        normalized = _normalize_url(url)
        if not normalized:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} Invalid URL: must start with http:// or https://")

        requester = gl.message.sender_address
        # Deterministic timestamp: comes from the message context, not a
        # wall clock (which would differ between leader and validators).
        timestamp = gl.message_raw["datetime"]

        def leader_fn():
            return _run_analysis(normalized)

        def validator_fn(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return _handle_leader_error(leaders_res, leader_fn)
            validator_data = leader_fn()
            return _compare_analysis(leaders_res.calldata, validator_data)

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        is_new = normalized not in self.reports
        self.reports[normalized] = Report(
            url=normalized,
            timestamp=timestamp,
            requester=requester,
            safe=result["safe"],
            phishing=result["phishing"],
            malware=result["malware"],
            gambling=result["gambling"],
            adult=result["adult"],
            official=result["official"],
            trust_score=u8(result["trust_score"]),
            risk_tier=result["risk_tier"],
            category=result["category"],
            reason=result["reason"],
            status="completed",
        )
        if is_new:
            self.analyzed_urls.append(normalized)

    # -- Reads ------------------------------------------------------------

    @gl.public.view
    def get_report(self, url: str) -> dict[str, typing.Any]:
        """Returns the latest full analysis for `url`. If it was never
        analyzed, returns an empty report with status="not_analyzed"."""
        normalized = _normalize_url(url)
        if normalized not in self.reports:
            return {
                "url": normalized,
                "timestamp": "",
                "requester": "",
                "safe": False,
                "phishing": False,
                "malware": False,
                "gambling": False,
                "adult": False,
                "official": False,
                "trust_score": 0,
                "risk_tier": "high_risk",
                "category": "Unknown",
                "reason": "",
                "status": "not_analyzed",
            }

        report = self.reports[normalized]
        return {
            "url": report.url,
            "timestamp": report.timestamp,
            "requester": report.requester.as_hex,
            "safe": report.safe,
            "phishing": report.phishing,
            "malware": report.malware,
            "gambling": report.gambling,
            "adult": report.adult,
            "official": report.official,
            "trust_score": int(report.trust_score),
            "risk_tier": report.risk_tier,
            "category": report.category,
            "reason": report.reason,
            "status": report.status,
        }

    @gl.public.view
    def is_safe(self, url: str) -> bool:
        normalized = _normalize_url(url)
        if normalized not in self.reports:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} URL has not been analyzed yet. Call analyze() first.")
        return self.reports[normalized].safe

    @gl.public.view
    def get_trust_score(self, url: str) -> u8:
        """Informational only. For automated pass/fail decisions, use
        `get_risk_tier` instead: it's the field consensus is actually
        gated on, so it can never straddle a decision-relevant boundary
        between two accepted results the way this raw number can."""
        normalized = _normalize_url(url)
        if normalized not in self.reports:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} URL has not been analyzed yet. Call analyze() first.")
        return self.reports[normalized].trust_score

    @gl.public.view
    def get_risk_tier(self, url: str) -> str:
        """Returns "trusted" | "caution" | "high_risk". This is the
        consensus-bound decision bucket derived from trust_score and the
        phishing/malware flags (see `_compute_risk_tier`). Consumers that
        need to make an automated accept/reject/warn decision should key
        off this field instead of applying their own threshold to
        `get_trust_score`."""
        normalized = _normalize_url(url)
        if normalized not in self.reports:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} URL has not been analyzed yet. Call analyze() first.")
        return self.reports[normalized].risk_tier

    @gl.public.view
    def get_category(self, url: str) -> str:
        normalized = _normalize_url(url)
        if normalized not in self.reports:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} URL has not been analyzed yet. Call analyze() first.")
        return self.reports[normalized].category

    @gl.public.view
    def has_report(self, url: str) -> bool:
        return _normalize_url(url) in self.reports

    @gl.public.view
    def get_analyzed_urls(self) -> DynArray[str]:
        return self.analyzed_urls

    @gl.public.view
    def get_total_analyses(self) -> u256:
        return u256(len(self.analyzed_urls))

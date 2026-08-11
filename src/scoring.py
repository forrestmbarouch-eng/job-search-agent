"""Weighted scoring against the user's stated search criteria.

Weights: seniority 30%, function 25%, industry 20%, location 15%, comp 10%.
Comp is scored neutral (0.5) for every role because none of the supported
platforms expose salary in their list-level JSON for Texas-based postings
(no state pay-transparency mandate compels disclosure) -- flagged explicitly
in the rationale rather than silently assumed.
"""
import re

WEIGHTS = {"seniority": 0.30, "function": 0.25, "industry": 0.20, "location": 0.15, "comp": 0.10}

DFW_KEYWORDS = [
    "dallas", "fort worth", "dfw", "plano", "irving", "richardson", "southlake",
    "westlake", "mckinney", "addison", "arlington, tx", "coppell", "frisco",
    "grapevine", "las colinas",
]

GM_OPS_KEYWORDS = [
    "business operations", "chief of staff", "general manager", r"\bgm\b",
    r"\bcoo\b", "chief operating officer", "business unit", "operating officer",
    "head of operations", "director of operations", "operations lead",
    r"\b(division|business unit|segment|regional|group|brand|market)\s+president\b",
    r"\bp&l\b",
]

STRATEGY_KEYWORDS = [
    "corporate strategy", r"\bstrategy\b", "strategic planning",
    "corporate development", r"\bm&a\b", "mergers", "business development",
]

BANKING_KEYWORDS = [r"\bbank\b", r"\bbanking\b"]
ADJACENT_FINANCE_KEYWORDS = [
    "financial services", "insurance", "wealth management", "asset management",
    "fintech",
]

SENIORITY_SCORES = {"VP": 1.0, "Senior Director": 0.85, "Director": 0.7}


def _match_any(patterns, text):
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def score_seniority(job):
    score = SENIORITY_SCORES.get(job["level"], 0.5)
    return score, f"Level detected: {job['level']}"


def score_function(job):
    title = job["title"]
    is_ops = _match_any(GM_OPS_KEYWORDS, title)
    is_strategy = _match_any(STRATEGY_KEYWORDS, title)
    if is_ops:
        return 1.0, "Business Ops / GM-track title match"
    if is_strategy:
        return 0.5, "Corporate Strategy title match — acceptable only if comp is materially higher; verify on listing"
    return 0.4, "No clear Ops or Strategy signal in title"


def score_industry(job):
    industry = job["industry"] or ""
    if _match_any(BANKING_KEYWORDS, industry):
        return 1.0, f"Banking/financial services: {industry}"
    if _match_any(ADJACENT_FINANCE_KEYWORDS, industry):
        return 0.6, f"Adjacent financial vertical: {industry}"
    return 0.3, f"Outside priority vertical: {industry}"


def score_location(job):
    loc = (job["location"] or "").lower()
    dfw_presence = (job["dfw_presence"] or "").lower()
    if _match_any(DFW_KEYWORDS, loc):
        return 1.0, f"Job location in DFW metro: {job['location']}"
    if "hybrid" in loc:
        return 0.7, f"Explicitly hybrid: {job['location']}"
    if not loc or loc == "remote":
        if _match_any(DFW_KEYWORDS, dfw_presence):
            return 0.5, f"Location unclear on listing; company has DFW presence ({job['dfw_presence']})"
        return 0.2, "Remote / non-DFW, no DFW company presence noted"
    return 0.2, f"Non-DFW location: {job['location']}"


def score_comp(job):
    return 0.5, "Comp not disclosed at listing level — verify manually (TX has no pay-transparency mandate)"


def score_job(job):
    seniority_s, seniority_note = score_seniority(job)
    function_s, function_note = score_function(job)
    industry_s, industry_note = score_industry(job)
    location_s, location_note = score_location(job)
    comp_s, comp_note = score_comp(job)

    total = (
        seniority_s * WEIGHTS["seniority"]
        + function_s * WEIGHTS["function"]
        + industry_s * WEIGHTS["industry"]
        + location_s * WEIGHTS["location"]
        + comp_s * WEIGHTS["comp"]
    )
    score_100 = round(total * 100, 1)

    rationale_parts = [seniority_note, function_note, industry_note, location_note]
    rationale = "; ".join(rationale_parts)

    job["score"] = score_100
    job["rationale"] = rationale
    job["comp_note"] = comp_note
    return job

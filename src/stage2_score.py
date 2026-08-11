"""Approximate the Airtable 'Executive Career Agent' rubric: sponsor tier,
trajectory-to-authority language, and comp-as-cap, layered on top of the
Stage 1 mechanical score.

This is a heuristic approximation built from regex/keyword pattern-matching
against job description text -- NOT a replication of per-role LLM judgment
(which is what actually produced the reference scores in Airtable). Treat
the numeric score and Recommendation bucket as a triage aid, not a verdict;
"Why It Fits" / "Concerns" text is templated from detected signals, not
independently reasoned per role.
"""
import re

PL_OWNING_TITLES = [
    r"chief executive officer", r"\bceo\b", r"chief operating officer", r"\bcoo\b",
    r"chief banking officer", r"chief commercial officer", r"chief revenue officer",
    r"chief growth officer", r"president\b", r"general manager", r"\bgm\b",
    r"business unit (?:president|leader|head)", r"division president",
    r"segment president", r"regional president", r"managing director",
]

FUNCTION_HEAD_TITLES = [
    r"chief technology officer", r"\bcto\b", r"chief information officer", r"\bcio\b",
    r"chief people officer", r"\bchro\b", r"chief marketing officer", r"\bcmo\b",
    r"chief legal officer", r"chief risk officer", r"chief compliance officer",
    r"chief architecture officer", r"chief engineering officer", r"chief product officer",
    r"\bcpo\b", r"chief customer (?:engagement )?officer", r"head of \w+ engineering",
    r"vice president of (?:engineering|architecture|technology|product)",
]

SPONSOR_PATTERNS = [
    re.compile(r"chief of staff to (?:the )?([A-Z][A-Za-z&,'\s]{3,60}?)(?:\.|,|\s+and\s|\s+who\s|\s+will\s|$)"),
    re.compile(r"reports? (?:directly )?to (?:the )?([A-Z][A-Za-z&,'\s]{3,60}?)(?:\.|,|\s+and\s|\s+who\s|$)"),
    re.compile(r"support(?:s|ing)? (?:the )?([A-Z][A-Za-z&,'\s]{3,60}?)(?:\.|,|\s+and\s|\s+in\s|$)"),
    re.compile(r"partner(?:ing|s)? (?:closely )?with (?:the )?([A-Z][A-Za-z&,'\s]{3,60}?)(?:\.|,|\s+and\s|\s+to\s|$)"),
]

TRAJECTORY_PATTERNS = [
    r"path to", r"future opportunity", r"grow into", r"succession", r"future leadership",
    r"will take on", r"expand(?:ing)? (?:your |their )?scope", r"growth (?:path|trajectory)",
    r"developing (?:future|next-generation) leaders",
]

COMP_RE = re.compile(r"\$([\d]{2,3}(?:,\d{3})?)\s*[kK]?\s*(?:-|to|–|—)\s*\$?([\d]{2,3}(?:,\d{3})?)\s*[kK]?")

DFW_KEYWORDS = [
    "dallas", "fort worth", "dfw", "plano", "irving", "richardson", "southlake",
    "westlake", "mckinney", "addison", "coppell", "frisco", "grapevine", "las colinas",
]


def _match_any(patterns, text):
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def classify_sponsor(description_text):
    text = description_text or ""
    sponsor_title = None
    for pattern in SPONSOR_PATTERNS:
        m = pattern.search(text)
        if m:
            sponsor_title = m.group(1).strip()
            break

    if not sponsor_title:
        return "No sponsor identified", None, 0.2
    if _match_any(PL_OWNING_TITLES, sponsor_title):
        return "P&L-owning", sponsor_title, 1.0
    if _match_any(FUNCTION_HEAD_TITLES, sponsor_title):
        return "Function head", sponsor_title, 0.55
    return "Unclear title", sponsor_title, 0.4


def detect_trajectory(description_text):
    text = description_text or ""
    if _match_any(TRAJECTORY_PATTERNS, text):
        return True, 1.0
    return False, 0.5


def resolve_location_score(resolved_locations, original_location_text):
    locs = [l for l in (resolved_locations or []) if l] or [original_location_text or ""]
    joined = " | ".join(locs).lower()
    if any(k in joined for k in DFW_KEYWORDS):
        return "DFW on-site/hybrid", 1.0, locs
    if "hybrid" in joined:
        return "Hybrid (non-DFW city)", 0.6, locs
    if "remote" in joined or "flexible" in joined or "virtual" in joined:
        return "Remote (national)", 0.5, locs
    return "Non-DFW, not remote", 0.0, locs


def comp_signal(description_text, target_floor=300000, equity_weight_threshold=262500):
    text = description_text or ""
    matches = COMP_RE.findall(text)
    if not matches:
        return None, "No comp figures found in description — verify manually", 0.5
    nums = []
    for lo, hi in matches:
        for v in (lo, hi):
            v_clean = v.replace(",", "")
            n = int(v_clean)
            if n < 1000:
                n *= 1000
            nums.append(n)
    if not nums:
        return None, "No comp figures found in description — verify manually", 0.5
    high = max(nums)
    low = min(nums)
    note = f"Description states ${low:,}-${high:,}"
    if high < target_floor * 0.8:
        return (low, high), note + " — likely well below $300K target, cap applied", 0.1
    if high < target_floor:
        return (low, high), note + " — may not clear $300K all-in without bonus/equity", 0.4
    equity_note = " — above equity-weighting threshold, confirm cash/equity mix" if high >= equity_weight_threshold else ""
    return (low, high), note + equity_note, 0.9


def score_candidate(row, description_text, resolved_locations):
    sponsor_tier, sponsor_title, sponsor_score = classify_sponsor(description_text)
    has_trajectory, trajectory_score = detect_trajectory(description_text)
    location_label, location_score, resolved = resolve_location_score(resolved_locations, row.get("location"))
    comp_range, comp_note, comp_score = comp_signal(description_text)

    stage1_score = float(row.get("score", 0)) / 100.0

    weights = {"stage1": 0.30, "sponsor": 0.30, "trajectory": 0.10, "location": 0.20, "comp": 0.10}
    raw = (
        stage1_score * weights["stage1"]
        + sponsor_score * weights["sponsor"]
        + trajectory_score * weights["trajectory"]
        + location_score * weights["location"]
        + comp_score * weights["comp"]
    )
    score_100 = round(raw * 100, 1)

    if comp_score <= 0.1:
        score_100 = min(score_100, 55)

    if score_100 >= 85:
        recommendation = "Priority Apply" if sponsor_tier == "P&L-owning" and location_score >= 0.6 else "Strong Review"
    elif score_100 >= 72:
        recommendation = "Strong Review"
    elif score_100 >= 60:
        recommendation = "Monitor"
    elif score_100 >= 45:
        recommendation = "Low Priority"
    else:
        recommendation = "Reject"

    why_it_fits = (
        f"{row['level']}-level role at {row['company']} ({row.get('industry', 'n/a')}); "
        f"sponsor signal: {sponsor_tier}" + (f" ({sponsor_title})" if sponsor_title else "") + "; "
        f"location: {location_label}" + (" with trajectory-to-authority language present" if has_trajectory else "")
    )
    concerns_parts = []
    if sponsor_tier in ("Unclear title", "No sponsor identified"):
        concerns_parts.append("Sponsor/reporting line not clearly identifiable from posting — verify before investing time")
    if not has_trajectory:
        concerns_parts.append("No explicit path-to-authority language found — may be a staff/execution role without a stated growth track")
    if comp_score <= 0.4:
        concerns_parts.append(comp_note)
    if location_score < 0.6:
        concerns_parts.append(f"Location may not satisfy DFW/relationship-density preference: {location_label}")
    concerns = "; ".join(concerns_parts) if concerns_parts else "None flagged by heuristic scan — still verify manually"

    return {
        "score": score_100,
        "recommendation": recommendation,
        "sponsor_tier": sponsor_tier,
        "sponsor_title": sponsor_title or "",
        "has_trajectory_language": has_trajectory,
        "location_label": location_label,
        "resolved_locations": resolved,
        "comp_range": comp_range,
        "comp_note": comp_note,
        "why_it_fits": why_it_fits,
        "concerns": concerns,
    }

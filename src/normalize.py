"""Normalize raw postings into a common shape and filter to Director+/VP-level roles."""
import re

LEVEL_EXCLUDE_RE = re.compile(
    r"\b(Assistant Director|Associate Director|Deputy Director|Intern|Internship|"
    r"Co[- ]?op|Entry[- ]?Level|Assistant Vice President|\bAVP\b)\b",
    re.IGNORECASE,
)

LEVEL_PATTERNS = [
    ("VP", re.compile(r"\b(EVP|SVP|Executive Vice President|Senior Vice President)\b", re.IGNORECASE)),
    ("VP", re.compile(r"\b(Vice President|VP)\b", re.IGNORECASE)),
    ("VP", re.compile(r"\b(President|General Manager|\bGM\b)\b", re.IGNORECASE)),
    ("Senior Director", re.compile(r"\b(Senior Director|Sr\.?\s?Director)\b", re.IGNORECASE)),
    ("Director", re.compile(r"\bDirector\b", re.IGNORECASE)),
]


def classify_level(title):
    if LEVEL_EXCLUDE_RE.search(title):
        return None
    for label, pattern in LEVEL_PATTERNS:
        if pattern.search(title):
            return label
    return None


def normalize_and_filter(raw_jobs, company):
    results = []
    for job in raw_jobs:
        title = (job.get("title") or "").strip()
        if not title:
            continue
        level = classify_level(title)
        if level is None:
            continue
        results.append(
            {
                "title": title,
                "company": company["name"],
                "location": (job.get("location") or "").strip(),
                "level": level,
                "link": job.get("link", ""),
                "industry": company["industry"],
                "dfw_presence": company["dfw_presence"],
                "source_platform": company["platform"],
                "source_confidence": company.get("confidence", "unknown"),
            }
        )
    return results

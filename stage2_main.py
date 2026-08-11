import csv
import json
import os
import re
import sys
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from detail_fetch import fetch_detail
from stage2_score import score_candidate

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config", "companies.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

DFW_KEYWORDS = [
    "dallas", "fort worth", "dfw", "plano", "irving", "richardson", "southlake",
    "westlake", "mckinney", "addison", "arlington, tx", "coppell", "frisco",
    "grapevine", "las colinas",
]
REMOTE_KEYWORDS = ["remote", "hybrid", "flexible", "work from home", "virtual"]

TOP_N = 40
AMBIGUOUS_POOL_CAP = 100

# Your real Airtable tracker's Role Family taxonomy never includes these tracks --
# only Business Ops/Strategy/Chief of Staff/GM/Corp Dev roles enter that funnel.
# Stage 1 only down-weighted function mismatch (25% of the score); that's not
# enough to keep e.g. "Enterprise Architect - Fraud Domain, Director" out of a
# top-40 list. Hard-exclude by title here instead.
OFF_TRACK_TITLE_RE = re.compile(
    r"\b(software|java|python|\.net|devops|site reliability|\bsre\b|"
    r"network engineer|systems engineer|infrastructure engineer|data engineer|"
    r"data scientist|machine learning|\bml\b engineer|database administrator|"
    r"enterprise architect|solutions architect|cloud architect|security architect|"
    r"technical architect|network architect|qa\b|quality assurance|"
    r"tax\b|actuary|actuarial|underwrit|auditor|internal audit|"
    r"attorney|legal counsel|general counsel|litigation|"
    r"accounting|accountant|payroll|"
    r"recruiter|talent acquisition|"
    r"nurse|clinical|physician|pharmacist|"
    r"engineering|cybersecurity|cyber security|information security|\binfosec\b|"
    r"technical program|it operations|network engineer|"
    r"developer experience)\b",
    re.IGNORECASE,
)


def is_off_track(title):
    return bool(OFF_TRACK_TITLE_RE.search(title or ""))


def classify_location(loc):
    l = (loc or "").lower()
    if any(k in l for k in DFW_KEYWORDS):
        return "dfw"
    if any(k in l for k in REMOTE_KEYWORDS):
        return "remote_or_hybrid"
    if "locations" in l or l.strip() == "":
        return "ambiguous"
    return "other"


def latest_stage1_csv():
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "shortlist_*.csv")))
    return files[-1]


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        companies = json.load(f)
    company_by_name = {c["name"]: c for c in companies}

    csv_path = latest_stage1_csv()
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["score"] = float(r["score"])

    on_track_rows = [r for r in rows if not is_off_track(r["title"])]
    excluded_count = len(rows) - len(on_track_rows)
    print(f"Off-track function titles excluded (Engineering/IT/Legal/Tax/Audit/Clinical/etc.): {excluded_count}")

    unambiguous = [r for r in on_track_rows if classify_location(r["location"]) in ("dfw", "remote_or_hybrid")]
    ambiguous = sorted(
        (r for r in on_track_rows if classify_location(r["location"]) == "ambiguous"),
        key=lambda r: r["score"], reverse=True,
    )[:AMBIGUOUS_POOL_CAP]

    candidate_pool = sorted(unambiguous + ambiguous, key=lambda r: r["score"], reverse=True)
    print(f"Stage 1 rows: {len(rows)} | unambiguous eligible: {len(unambiguous)} | ambiguous pulled for resolution: {len(ambiguous)}")
    print(f"Candidate pool sent to detail fetch: {len(candidate_pool)}")

    for row in candidate_pool:
        company = company_by_name.get(row["company"])
        if company is None:
            continue
        ident = company["id"]
        row["_board_token"] = ident.get("board_token")
        row["_slug"] = ident.get("slug")
        row["_org"] = ident.get("org")

    resolved = []
    failed = []
    for i, row in enumerate(candidate_pool):
        detail, err = fetch_detail(row)
        if err or not detail:
            failed.append((row["company"], row["title"], err))
            continue
        loc_class = classify_location(" | ".join(detail["resolved_locations"]))
        if loc_class not in ("dfw", "remote_or_hybrid"):
            continue
        scored = score_candidate(row, detail["description_text"], detail["resolved_locations"])
        merged = {**row, **scored}
        resolved.append(merged)
        if (i + 1) % 20 == 0:
            print(f"  processed {i + 1}/{len(candidate_pool)}, {len(resolved)} eligible so far")

    print(f"Detail fetch failures: {len(failed)}")
    for company, title, err in failed[:10]:
        print(f"  [FAIL] {company} - {title}: {err}")

    resolved.sort(key=lambda r: r["score"], reverse=True)
    top = resolved[:TOP_N]

    out_path = os.path.join(OUTPUT_DIR, "stage2_scored.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(top, f, indent=2)

    print(f"\nDFW/remote-eligible after resolution: {len(resolved)}")
    print(f"Writing top {len(top)} to {out_path}")
    for r in top[:15]:
        print(f"  {r['score']:>5} | {r['recommendation']:<14} | {r['company']:<25} | {r['title']}")


if __name__ == "__main__":
    main()

import json
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fetchers import fetch_company
from normalize import normalize_and_filter
from scoring import score_job
from output import write_markdown, write_csv

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "companies.json")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        companies = json.load(f)

    all_jobs = []
    errors = []

    for company in companies:
        raw_jobs, error = fetch_company(company)
        if error:
            errors.append((company["name"], error))
            print(f"[FAIL] {company['name']} ({company['platform']}): {error}")
            continue
        filtered = normalize_and_filter(raw_jobs, company)
        print(f"[OK]   {company['name']} ({company['platform']}): {len(raw_jobs)} postings -> {len(filtered)} Director+/VP")
        all_jobs.extend(filtered)

    scored = [score_job(j) for j in all_jobs]
    scored.sort(key=lambda j: j["score"], reverse=True)

    today = date.today().isoformat()
    md_path = os.path.join(OUTPUT_DIR, f"shortlist_{today}.md")
    csv_path = os.path.join(OUTPUT_DIR, f"shortlist_{today}.csv")
    write_markdown(scored, md_path)
    write_csv(scored, csv_path)

    print()
    print(f"Total companies queried: {len(companies)}")
    print(f"Companies that failed to fetch: {len(errors)}")
    for name, err in errors:
        print(f"  - {name}: {err}")
    print(f"Total Director+/VP roles found: {len(scored)}")
    print(f"Markdown -> {md_path}")
    print(f"CSV -> {csv_path}")


if __name__ == "__main__":
    main()

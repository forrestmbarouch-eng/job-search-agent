"""Render ranked job list as Markdown and CSV."""
import csv


def write_markdown(jobs, path):
    lines = [
        f"# Job Search Shortlist — {len(jobs)} roles",
        "",
        "| Score | Title | Company | Location | Level | Source | Rationale |",
        "|---|---|---|---|---|---|---|",
    ]
    for j in jobs:
        source_tag = j["source_platform"] + ("*" if j["source_platform"] == "workday" else "")
        title_link = f"[{j['title']}]({j['link']})" if j["link"] else j["title"]
        lines.append(
            f"| {j['score']} | {title_link} | {j['company']} | {j['location']} | "
            f"{j['level']} | {source_tag} | {j['rationale']} |"
        )
    lines.append("")
    lines.append("\\* Workday-sourced: pulled from the career site's own internal API, not a documented public endpoint. Treat as best-effort.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_csv(jobs, path):
    fields = ["score", "title", "company", "location", "level", "link", "source_platform", "rationale", "comp_note"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for j in jobs:
            writer.writerow(j)

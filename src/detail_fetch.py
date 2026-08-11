"""Fetch full job descriptions and resolve true location for Stage 2 candidates."""
import re
import time
import requests

USER_AGENT = "job-search-agent/0.1 (personal use, weekly manual run)"
TIMEOUT = 20

TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html):
    text = TAG_RE.sub(" ", html or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_workday_link(link):
    """https://{tenant}.{host}.myworkdayjobs.com/{site}/job/{path} -> (tenant, host, site, job_path)"""
    m = re.match(r"https://([^.]+)\.([^.]+)\.myworkdayjobs\.com/([^/]+)/job/(.+)", link)
    if not m:
        return None
    tenant, host, site, job_path = m.groups()
    return tenant, host, site, job_path


def fetch_workday_detail(link):
    parsed = parse_workday_link(link)
    if not parsed:
        return None, "could not parse workday link"
    tenant, host, site, job_path = parsed
    url = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{job_path}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        info = resp.json().get("jobPostingInfo", {})
        locations = [info.get("location", "")] + [
            l.get("descriptor", "") if isinstance(l, dict) else str(l)
            for l in info.get("additionalLocations", []) or []
        ]
        return {
            "description_text": strip_html(info.get("jobDescription", "")),
            "resolved_locations": [l for l in locations if l],
        }, None
    except requests.exceptions.RequestException as e:
        return None, str(e)
    except ValueError as e:
        return None, f"bad json: {e}"


_gh_cache = {}
_lever_cache = {}
_ashby_cache = {}


def fetch_greenhouse_detail(link, board_token):
    if board_token not in _gh_cache:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        _gh_cache[board_token] = {j["absolute_url"]: j for j in resp.json().get("jobs", [])}
    job = _gh_cache[board_token].get(link)
    if not job:
        return None, "job not found in board refetch"
    return {
        "description_text": strip_html(job.get("content", "")),
        "resolved_locations": [job.get("location", {}).get("name", "")],
    }, None


def fetch_lever_detail(link, slug):
    if slug not in _lever_cache:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        _lever_cache[slug] = {p["hostedUrl"]: p for p in resp.json()}
    job = _lever_cache[slug].get(link)
    if not job:
        return None, "job not found in board refetch"
    desc = job.get("descriptionPlain") or strip_html(job.get("description", ""))
    lists_text = " ".join(
        strip_html(item.get("text", "")) + " " + " ".join(strip_html(c) for c in item.get("content", []))
        for item in job.get("lists", []) or []
    )
    return {
        "description_text": (desc or "") + " " + lists_text,
        "resolved_locations": [(job.get("categories") or {}).get("location", "")],
    }, None


def fetch_ashby_detail(link, org):
    if org not in _ashby_cache:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        _ashby_cache[org] = {j.get("jobUrl"): j for j in resp.json().get("jobs", [])}
    job = _ashby_cache[org].get(link)
    if not job:
        return None, "job not found in board refetch"
    return {
        "description_text": strip_html(job.get("descriptionHtml", "") or job.get("descriptionPlain", "")),
        "resolved_locations": [job.get("location", "")],
    }, None


def fetch_detail(row):
    platform = row["source_platform"]
    link = row["link"]
    try:
        if platform == "workday":
            result, err = fetch_workday_detail(link)
        elif platform == "greenhouse":
            result, err = fetch_greenhouse_detail(link, row["_board_token"])
        elif platform == "lever":
            result, err = fetch_lever_detail(link, row["_slug"])
        elif platform == "ashby":
            result, err = fetch_ashby_detail(link, row["_org"])
        else:
            return None, f"unsupported platform {platform}"
        return result, err
    finally:
        time.sleep(0.2)

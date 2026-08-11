"""Pull raw job postings from each supported ATS platform's public JSON endpoint."""
import time
import requests

USER_AGENT = "job-search-agent/0.1 (personal use, weekly manual run)"
TIMEOUT = 20

WORKDAY_LEVEL_QUERIES = ["Director", "Vice President", "VP", "Senior Director"]


def fetch_greenhouse(board_token):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])
    return [
        {
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "link": j.get("absolute_url", ""),
        }
        for j in jobs
    ]


def fetch_lever(slug):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    postings = resp.json()
    return [
        {
            "title": p.get("text", ""),
            "location": (p.get("categories") or {}).get("location", ""),
            "link": p.get("hostedUrl", ""),
        }
        for p in postings
    ]


def fetch_ashby(org):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])
    return [
        {
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "link": j.get("jobUrl", ""),
        }
        for j in jobs
    ]


def fetch_workday(tenant, host, site):
    """Query the tenant's public CXS endpoint once per seniority keyword and
    de-dupe by externalPath. This endpoint is not a documented public API --
    it's what the career site's own browser client calls -- so treat results
    as best-effort and flag failures rather than raising loudly."""
    base = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    seen = {}
    for query in WORKDAY_LEVEL_QUERIES:
        offset = 0
        limit = 20
        while True:
            body = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": query}
            resp = requests.post(
                base,
                json=body,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            postings = data.get("jobPostings", [])
            for p in postings:
                path = p.get("externalPath", "")
                if path and path not in seen:
                    seen[path] = {
                        "title": p.get("title", ""),
                        "location": p.get("locationsText", ""),
                        "link": f"https://{tenant}.{host}.myworkdayjobs.com/{site}{path}",
                    }
            total = data.get("total", 0)
            offset += limit
            if offset >= min(total, 100) or not postings:
                break
            time.sleep(0.3)
        time.sleep(0.3)
    return list(seen.values())


def fetch_company(company):
    platform = company["platform"]
    ident = company["id"]
    try:
        if platform == "greenhouse":
            return fetch_greenhouse(ident["board_token"]), None
        if platform == "lever":
            return fetch_lever(ident["slug"]), None
        if platform == "ashby":
            return fetch_ashby(ident["org"]), None
        if platform == "workday":
            return fetch_workday(ident["tenant"], ident["host"], ident["site"]), None
        return [], f"unknown platform: {platform}"
    except requests.exceptions.RequestException as e:
        return [], str(e)

import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from digest.config import Config
from digest.models import FundedCompany, JobListing

logger = logging.getLogger(__name__)

ATS_PATTERNS = {
    "lever": r"lever\.co\/([^/?#]+)",
    "greenhouse": r"(?:boards|greenhouse)\.io\/([^/?#]+)",
    "ashby": r"ashbyhq\.com\/([^/?#]+)",
    "workable": r"jobs\.workable\.com\/([^/?#]+)",
    "smartrecruiters": r"careers\.smartrecruiters\.com\/([^/?#]+)",
}

DEPARTMENT_MAP = {
    "Engineering": ["engineer", "engineering", "developer", "backend", "frontend", "fullstack", "full-stack", "software"],
    "AI/ML": ["machine learning", "ml", "ai ", " ai", "llm", "scientist", "research"],
    "Data": ["data analyst", "data engineer", "data science", "analytics", "analyst"],
    "Infrastructure": ["devops", "sre", "platform", "infrastructure", "cloud", "infra", "reliability"],
    "Product": ["product manager", "pm ", " pm", "product lead", "product owner"],
    "Security": ["security", "appsec", "infosec", "pen test", "pentest"],
}


def scrape_careers(company: FundedCompany, session: requests.Session, config: Config) -> list:
    if not company.careers_url:
        return []

    time.sleep(0.5)  # polite delay

    ats = _detect_ats(company.careers_url)
    jobs = []

    try:
        if ats == "lever":
            jobs = _scrape_lever(company.careers_url, session)
        elif ats == "greenhouse":
            jobs = _scrape_greenhouse(company.careers_url, session)
        elif ats == "ashby":
            jobs = _scrape_ashby(company.careers_url, session)
        elif ats == "workable":
            jobs = _scrape_workable(company.careers_url, session)
        else:
            jobs = _scrape_generic(company.careers_url, session)
    except Exception as e:
        logger.warning(f"Careers scrape failed for {company.name} ({company.careers_url}): {e}")
        # Try generic as fallback if ATS scraper failed
        if ats and ats != "generic":
            try:
                jobs = _scrape_generic(company.careers_url, session)
            except Exception:
                pass

    tech_jobs = [j for j in jobs if _is_tech_role(j.title, config)]
    return tech_jobs[:config.MAX_JOBS_PER_CO]


def _detect_ats(url: str) -> Optional[str]:
    for ats, pattern in ATS_PATTERNS.items():
        if re.search(pattern, url, re.I):
            return ats
    return None


def _scrape_lever(url: str, session: requests.Session) -> list:
    match = re.search(r"lever\.co\/([^/?#]+)", url, re.I)
    if not match:
        return []

    slug = match.group(1)
    api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = session.get(api_url, timeout=10)
    if not resp.ok:
        return []

    jobs = []
    for posting in resp.json():
        title = posting.get("text", "")
        location = posting.get("categories", {}).get("location", "Remote")
        apply_url = posting.get("hostedUrl", url)
        jobs.append(JobListing(
            title=title,
            location=location or "Remote",
            url=apply_url,
            department=_infer_department(title),
        ))
    return jobs


def _scrape_greenhouse(url: str, session: requests.Session) -> list:
    match = re.search(r"(?:boards|greenhouse)\.io\/([^/?#]+)", url, re.I)
    if not match:
        return []

    slug = match.group(1)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    resp = session.get(api_url, timeout=10)
    if not resp.ok:
        return []

    jobs = []
    data = resp.json()
    for job in data.get("jobs", []):
        title = job.get("title", "")
        location = job.get("location", {}).get("name", "Remote")
        apply_url = job.get("absolute_url", url)
        jobs.append(JobListing(
            title=title,
            location=location or "Remote",
            url=apply_url,
            department=_infer_department(title),
        ))
    return jobs


def _scrape_ashby(url: str, session: requests.Session) -> list:
    match = re.search(r"ashbyhq\.com\/([^/?#]+)", url, re.I)
    if not match:
        return []

    slug = match.group(1)
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    resp = session.post(api_url, json={"organizationHostedJobsPageName": slug}, timeout=10)
    if not resp.ok:
        return []

    jobs = []
    data = resp.json()
    for job in data.get("jobPostings", []):
        title = job.get("title", "")
        location = job.get("locationName", "Remote")
        apply_url = job.get("jobPostingPath", "")
        if apply_url and not apply_url.startswith("http"):
            apply_url = f"https://jobs.ashbyhq.com/{slug}/{apply_url}"
        jobs.append(JobListing(
            title=title,
            location=location or "Remote",
            url=apply_url or url,
            department=_infer_department(title),
        ))
    return jobs


def _scrape_workable(url: str, session: requests.Session) -> list:
    match = re.search(r"jobs\.workable\.com\/([^/?#]+)", url, re.I)
    if not match:
        return []

    slug = match.group(1)
    api_url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}/jobs"
    resp = session.get(api_url, timeout=10)
    if not resp.ok:
        return _scrape_generic(url, session)

    jobs = []
    data = resp.json()
    for job in data.get("results", []):
        title = job.get("title", "")
        location = job.get("location", {}).get("city", "Remote")
        apply_url = job.get("url", url)
        jobs.append(JobListing(
            title=title,
            location=location or "Remote",
            url=apply_url,
            department=_infer_department(title),
        ))
    return jobs


def _scrape_generic(url: str, session: requests.Session) -> list:
    resp = session.get(url, timeout=12)
    if not resp.ok:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    jobs = []
    base_domain = f"https://{urlparse(url).netloc}"

    # Strategy 1: look for job-list containers
    job_containers = soup.find_all(
        ["div", "li", "section", "article"],
        class_=re.compile(r"job|position|opening|role|listing|career", re.I)
    )

    if job_containers:
        for container in job_containers[:30]:
            link = container.find("a", href=True)
            if not link:
                continue

            title = link.get_text(strip=True) or container.get_text(strip=True)[:80]
            href = link.get("href", "")
            if not href.startswith("http"):
                href = base_domain + href

            location = _extract_location(container.get_text())

            if len(title) > 5:
                jobs.append(JobListing(
                    title=title.strip(),
                    location=location,
                    url=href,
                    department=_infer_department(title),
                ))
    else:
        # Strategy 2: find all internal links that look like job postings
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")

            if len(text) < 5 or len(text) > 100:
                continue

            if not href.startswith("http"):
                href = base_domain + href

            if urlparse(href).netloc != urlparse(url).netloc:
                continue

            if _looks_like_job_link(text, href):
                jobs.append(JobListing(
                    title=text,
                    location="Remote",
                    url=href,
                    department=_infer_department(text),
                ))

    return jobs


def _looks_like_job_link(text: str, href: str) -> bool:
    job_path_patterns = ["/job", "/role", "/position", "/opening", "/careers/"]
    text_lower = text.lower()
    href_lower = href.lower()

    has_job_path = any(p in href_lower for p in job_path_patterns)
    has_tech_word = any(kw in text_lower for kw in [
        "engineer", "developer", "data", "product", "design",
        "manager", "scientist", "analyst", "architect",
    ])
    return has_job_path or has_tech_word


def _extract_location(text: str) -> str:
    text_lower = text.lower()
    if "remote" in text_lower:
        return "Remote"

    location_patterns = [
        r'\b(New York|NYC|San Francisco|SF|Seattle|Austin|Boston|Chicago|London|Berlin|Toronto|Denver|LA|Los Angeles|Atlanta|Miami)\b'
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)

    return "See listing"


def _is_tech_role(title: str, config: Config) -> bool:
    title_lower = title.lower()

    # Check exclude list first
    for excl in config.EXCLUDE_KEYWORDS:
        if excl in title_lower:
            return False

    # Check include keywords
    for kw in config.TECH_KEYWORDS:
        if kw in title_lower:
            return True

    return False


def _infer_department(title: str) -> str:
    title_lower = title.lower()
    for dept, keywords in DEPARTMENT_MAP.items():
        if any(kw in title_lower for kw in keywords):
            return dept
    return "Tech"

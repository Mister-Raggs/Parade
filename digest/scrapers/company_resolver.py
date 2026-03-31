import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz

from digest.models import FundedCompany

logger = logging.getLogger(__name__)

CAREERS_PATHS = [
    "/careers", "/jobs", "/join", "/work-with-us", "/join-us",
    "/about/careers", "/about/jobs", "/company/jobs", "/open-roles",
    "/positions", "/team", "/hiring",
]

ATS_PATTERNS = {
    "lever": r"lever\.co\/([^/?#]+)",
    "greenhouse": r"(?:boards|greenhouse)\.io\/([^/?#]+)",
    "ashby": r"ashbyhq\.com\/([^/?#]+)",
    "workable": r"jobs\.workable\.com\/([^/?#]+)",
    "smartrecruiters": r"careers\.smartrecruiters\.com\/([^/?#]+)",
}


def resolve_company(company: FundedCompany, session: requests.Session) -> None:
    # Try to find website via 3-tier fallback
    website = None
    resolution_method = None

    website = _extract_website_from_article(company.source_url, company.name, session)
    if website:
        resolution_method = "article_parse"
    else:
        website = _clearbit_lookup(company.name)
        if website:
            resolution_method = "clearbit"
        else:
            website = _duckduckgo_search(company.name, session)
            if website:
                resolution_method = "duckduckgo"

    if not website:
        logger.warning(
            f"Could not resolve website for: {company.name} | "
            f"resolved=false methods_tried=article_parse,clearbit,duckduckgo"
        )
        return

    company.website = website
    company.resolution_method = resolution_method
    logger.info(f"  Resolved: {company.name} -> {website} | method={resolution_method}")

    company.careers_url = _find_careers_url(website, session)

    if company.careers_url:
        careers_method = "ats_link" if any(
            re.search(p, company.careers_url, re.I) for p in ATS_PATTERNS.values()
        ) else "common_path_or_homepage"
        logger.info(f"  Careers URL: {company.careers_url} | method={careers_method}")
    else:
        logger.warning(f"  No careers URL found for: {company.name} ({website})")


def _extract_website_from_article(article_url: str, company_name: str, session: requests.Session) -> Optional[str]:
    if not article_url:
        return None

    try:
        resp = session.get(article_url, timeout=10)
        if not resp.ok:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        article_body = soup.find("article") or soup.find("div", class_=re.compile(r"post|article|content", re.I))

        if not article_body:
            return None

        company_lower = company_name.lower()
        for a in article_body.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True).lower()

            # Skip TC internal links, social media, etc.
            if any(skip in href for skip in ["techcrunch.com", "twitter.com", "linkedin.com", "facebook.com", "crunchbase.com", "#", "javascript:"]):
                continue

            if not href.startswith("http"):
                continue

            parsed = urlparse(href)
            domain = parsed.netloc.lower().replace("www.", "")

            # Check if domain or link text resembles company name
            name_words = company_lower.split()
            if any(word in domain for word in name_words if len(word) > 3):
                return f"https://{parsed.netloc}"

            if fuzz.partial_ratio(company_lower, text) > 80:
                return f"https://{parsed.netloc}"

    except Exception as e:
        logger.debug(f"Article parse failed for {article_url}: {e}")

    return None


def _clearbit_lookup(company_name: str) -> Optional[str]:
    try:
        url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={requests.utils.quote(company_name)}"
        resp = requests.get(url, timeout=8)
        if not resp.ok:
            return None

        results = resp.json()
        if not results:
            return None

        # Pick best match by name similarity
        for result in results[:3]:
            name = result.get("name", "")
            domain = result.get("domain", "")
            if domain and fuzz.token_sort_ratio(company_name.lower(), name.lower()) > 70:
                return f"https://{domain}"

    except Exception as e:
        logger.debug(f"Clearbit lookup failed for {company_name}: {e}")

    return None


def _duckduckgo_search(company_name: str, session: requests.Session) -> Optional[str]:
    time.sleep(2)  # polite delay before DDG
    try:
        query = requests.utils.quote(f"{company_name} official site")
        url = f"https://html.duckduckgo.com/html/?q={query}"
        resp = session.get(url, timeout=10)
        if not resp.ok:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        for result in soup.select(".result__url"):
            href = result.get("href", "")
            if href and "http" in href:
                parsed = urlparse(href)
                if parsed.netloc:
                    skip = ["duckduckgo.com", "wikipedia.org", "linkedin.com",
                            "twitter.com", "facebook.com", "crunchbase.com"]
                    if not any(s in parsed.netloc for s in skip):
                        return f"https://{parsed.netloc}"

    except Exception as e:
        logger.debug(f"DuckDuckGo search failed for {company_name}: {e}")

    return None


def _find_careers_url(base_url: str, session: requests.Session) -> Optional[str]:
    # Check common paths first
    for path in CAREERS_PATHS:
        try:
            url = urljoin(base_url, path)
            resp = session.head(url, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                return url
        except Exception:
            continue

    # Parse homepage for careers link
    try:
        resp = session.get(base_url, timeout=10)
        if not resp.ok:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        careers_keywords = ["careers", "jobs", "work with us", "join our team", "join us", "we're hiring", "open roles"]

        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            href = a.get("href", "")

            if any(kw in text for kw in careers_keywords):
                if href.startswith("http"):
                    return href
                else:
                    return urljoin(base_url, href)

            # Check href itself for ATS patterns
            for ats, pattern in ATS_PATTERNS.items():
                if re.search(pattern, href, re.I):
                    return href if href.startswith("http") else urljoin(base_url, href)

    except Exception as e:
        logger.debug(f"Homepage careers link search failed for {base_url}: {e}")

    return None

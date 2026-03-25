import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import requests
from thefuzz import fuzz

from digest.config import Config
from digest.models import FundedCompany

logger = logging.getLogger(__name__)

AMOUNT_PATTERN = re.compile(
    r'\$\s*[\d,.]+\s*(?:million|billion|[MBK])\b', re.IGNORECASE
)
ROUND_PATTERN = re.compile(
    r'\b(Pre-?Seed|Seed|Series [A-F]|Growth|Late Stage|Bridge)\b', re.IGNORECASE
)
FUNDING_SIGNALS = [
    "raises", "raised", "secures", "secured", "lands", "landed",
    "closes", "closed", "gets", "funding", "investment", "backed",
    "series a", "series b", "series c", "seed round", "seed funding",
]
SPLIT_WORDS = [
    " raises ", " raised ", " secures ", " secured ",
    " lands ", " landed ", " closes ", " closed ",
    " gets ", " nabs ", " snags ",
]


def fetch_all_feeds(config: Config, session: requests.Session) -> list:
    all_companies: list[FundedCompany] = []
    seen_names: list[str] = []
    feed_stats = []

    for feed_url in config.RSS_FEEDS:
        stats = {"url": feed_url, "entries_found": 0, "duplicates_skipped": 0, "error": None}
        try:
            companies = fetch_feed(feed_url, config.LOOKBACK_HOURS, session)
            stats["entries_found"] = len(companies)
            for company in companies:
                if _is_duplicate(company.name, seen_names):
                    stats["duplicates_skipped"] += 1
                    logger.info(f"  Dedup: skipped '{company.name}' (similar to existing)")
                else:
                    all_companies.append(company)
                    seen_names.append(company.name)
                    if len(all_companies) >= config.MAX_COMPANIES:
                        logger.info(f"  Reached max companies limit ({config.MAX_COMPANIES})")
                        feed_stats.append(stats)
                        _log_feed_summary(feed_stats)
                        return all_companies
        except Exception as e:
            stats["error"] = str(e)
            logger.warning(f"Failed to fetch feed {feed_url}: {e}")
        feed_stats.append(stats)

    _log_feed_summary(feed_stats)
    return all_companies


def _log_feed_summary(feed_stats: list) -> None:
    logger.info("--- RSS Feed Summary ---")
    for stats in feed_stats:
        status = "ERROR" if stats["error"] else "OK"
        logger.info(
            f"  {stats['url']} | status={status} "
            f"entries={stats['entries_found']} dupes_skipped={stats['duplicates_skipped']}"
        )
        if stats["error"]:
            logger.info(f"    error: {stats['error']}")


def fetch_feed(url: str, lookback_hours: int, session: requests.Session) -> list:
    logger.info(f"Fetching RSS: {url}")
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    companies = []
    total_entries = len(feed.entries)
    skipped_old = 0
    skipped_no_signal = 0
    skipped_no_name = 0

    for entry in feed.entries:
        try:
            published = _parse_published(entry)
            if published and published < cutoff:
                skipped_old += 1
                continue

            company = parse_entry(entry)
            if company:
                logger.info(
                    f"  Matched: {company.name} | amount={company.funding_amount or 'N/A'} "
                    f"round={company.funding_round or 'N/A'}"
                )
                companies.append(company)
        except Exception as e:
            logger.debug(f"Skipping entry: {e}")

    logger.info(
        f"Feed {url} | total_entries={total_entries} matched={len(companies)} "
        f"skipped_old={skipped_old} skipped_no_funding={total_entries - len(companies) - skipped_old}"
    )
    return companies


def parse_entry(entry) -> Optional[FundedCompany]:
    title = getattr(entry, 'title', '') or ''
    summary_raw = getattr(entry, 'summary', '') or ''
    source_url = getattr(entry, 'link', '') or ''

    # Strip HTML from summary
    summary = re.sub(r'<[^>]+>', ' ', summary_raw).strip()
    summary = re.sub(r'\s+', ' ', summary)

    full_text = f"{title} {summary}"

    if not _has_funding_signal(full_text):
        return None

    company_name = _extract_company_name(title)
    if not company_name or len(company_name) < 2:
        return None

    funding_amount, funding_round = _extract_funding_info(full_text)

    description = _extract_description(summary, company_name)

    return FundedCompany(
        name=company_name,
        source_url=source_url,
        funding_amount=funding_amount,
        funding_round=funding_round,
        description=description,
    )


def _has_funding_signal(text: str) -> bool:
    text_lower = text.lower()
    return any(signal in text_lower for signal in FUNDING_SIGNALS)


def _extract_company_name(title: str) -> Optional[str]:
    title = title.strip()

    # Try splitting on common verbs
    for word in SPLIT_WORDS:
        if word.lower() in title.lower():
            idx = title.lower().index(word.lower())
            name = title[:idx].strip()
            name = _clean_company_name(name)
            if name:
                return name

    # Fallback: take first 1-3 words if title looks like "CompanyName does X"
    words = title.split()
    if len(words) >= 2:
        candidate = ' '.join(words[:3])
        candidate = _clean_company_name(candidate)
        if candidate and len(candidate) > 1:
            return candidate

    return None


def _clean_company_name(name: str) -> str:
    # Remove leading articles/words
    prefixes = ['why ', 'how ', 'the ', 'a ', 'an ', 'yc-backed ', 'yc backed ']
    lower = name.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            name = name[len(prefix):]
            break

    # Remove trailing punctuation and suffixes
    name = name.strip(' .,;:')
    suffixes = [' Inc', ' Inc.', ' LLC', ' Ltd', ' Corp', ' Corporation']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    return name.strip()


def _extract_funding_info(text: str) -> tuple:
    amount_match = AMOUNT_PATTERN.search(text)
    round_match = ROUND_PATTERN.search(text)

    amount = amount_match.group(0).strip() if amount_match else None
    round_type = round_match.group(1).title() if round_match else None

    # Normalize amount
    if amount:
        amount = re.sub(r'\s+', '', amount)  # "$25 M" -> "$25M"

    return amount, round_type


def _extract_description(summary: str, company_name: str) -> Optional[str]:
    if not summary:
        return None

    # Take first 2 sentences
    sentences = re.split(r'(?<=[.!?])\s+', summary)
    desc = ' '.join(sentences[:2]).strip()

    # Truncate if too long
    if len(desc) > 300:
        desc = desc[:297] + '...'

    return desc if len(desc) > 20 else None


def _parse_published(entry) -> Optional[datetime]:
    published_parsed = getattr(entry, 'published_parsed', None)
    if published_parsed:
        return datetime(*published_parsed[:6], tzinfo=timezone.utc)
    return None


def _is_duplicate(name: str, seen_names: list) -> bool:
    for seen in seen_names:
        if fuzz.token_sort_ratio(name.lower(), seen.lower()) > 85:
            return True
    return False

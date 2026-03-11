import logging
import sys
from datetime import datetime

from digest.config import Config
from digest.email_sender.renderer import render_digest, render_plain_text
from digest.email_sender.sender import send_digest
from digest.scrapers.careers_scraper import scrape_careers
from digest.scrapers.company_resolver import resolve_company
from digest.scrapers.rss_scraper import fetch_all_feeds
from digest.utils import get_http_session, setup_logging

logger = logging.getLogger(__name__)


def run():
    setup_logging()
    logger.info("Starting Parade Digest...")

    config = Config()
    session = get_http_session()
    date_str = datetime.now().strftime("%B %d, %Y")

    # Stage 1: Fetch funded companies from RSS
    logger.info("Stage 1: Fetching RSS feeds...")
    companies = fetch_all_feeds(config, session)
    logger.info(f"Found {len(companies)} funded companies")

    if not companies:
        logger.warning("No funded companies found. Sending empty digest.")

    # Stage 2: Resolve websites + careers URLs
    logger.info("Stage 2: Resolving company websites and careers pages...")
    for i, company in enumerate(companies, 1):
        logger.info(f"  [{i}/{len(companies)}] Resolving: {company.name}")
        try:
            resolve_company(company, session)
        except Exception as e:
            logger.warning(f"  Failed to resolve {company.name}: {e}")

    # Stage 3: Scrape careers pages for tech roles
    logger.info("Stage 3: Scraping careers pages...")
    for i, company in enumerate(companies, 1):
        if company.careers_url:
            logger.info(f"  [{i}/{len(companies)}] Scraping jobs: {company.name}")
            try:
                company.jobs = scrape_careers(company, session, config)
                logger.info(f"    Found {len(company.jobs)} tech roles")
            except Exception as e:
                logger.warning(f"  Failed to scrape jobs for {company.name}: {e}")
        else:
            logger.info(f"  [{i}/{len(companies)}] Skipping (no careers URL): {company.name}")

    total_jobs = sum(len(c.jobs) for c in companies)
    logger.info(f"Total: {len(companies)} companies, {total_jobs} tech roles found")

    # Stage 4: Render email
    logger.info("Stage 4: Rendering email...")
    html = render_digest(companies, date_str)
    plain = render_plain_text(companies, date_str)

    companies_with_jobs = len([c for c in companies if c.jobs])
    subject = f"Parade Digest — {date_str}: {companies_with_jobs} funded companies hiring, {total_jobs} tech roles"

    # Stage 5: Send
    logger.info("Stage 5: Sending email...")
    send_digest(html, plain, subject, config)

    logger.info("Done.")


if __name__ == "__main__":
    run()

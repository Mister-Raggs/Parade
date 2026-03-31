import logging
import sys
import time
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
    pipeline_start = time.time()

    config = Config()
    session = get_http_session()
    date_str = datetime.now().strftime("%B %d, %Y")

    # Stage 1: Fetch funded companies from RSS
    logger.info("Stage 1: Fetching RSS feeds...")
    t0 = time.time()
    companies = fetch_all_feeds(config, session)
    stage1_time = time.time() - t0
    logger.info(f"Found {len(companies)} funded companies ({stage1_time:.1f}s)")

    if not companies:
        logger.warning("No funded companies found. Sending empty digest.")

    # Stage 2: Resolve websites + careers URLs
    logger.info("Stage 2: Resolving company websites and careers pages...")
    t0 = time.time()
    for i, company in enumerate(companies, 1):
        logger.info(f"  [{i}/{len(companies)}] Resolving: {company.name}")
        try:
            resolve_company(company, session)
        except Exception as e:
            logger.warning(f"  Failed to resolve {company.name}: {e}")
    stage2_time = time.time() - t0

    # Stage 3: Scrape careers pages for tech roles
    logger.info("Stage 3: Scraping careers pages...")
    t0 = time.time()
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
    stage3_time = time.time() - t0

    # Stage 4: Render email
    logger.info("Stage 4: Rendering email...")
    html = render_digest(companies, date_str)
    plain = render_plain_text(companies, date_str)

    companies_with_jobs = len([c for c in companies if c.jobs])
    total_jobs = sum(len(c.jobs) for c in companies)
    subject = f"Parade Digest — {date_str}: {companies_with_jobs} funded companies hiring, {total_jobs} tech roles"

    # Stage 5: Send
    logger.info("Stage 5: Sending email...")
    send_digest(html, plain, subject, config)

    # --- Run Summary ---
    pipeline_time = time.time() - pipeline_start
    websites_resolved = len([c for c in companies if c.website])
    careers_found = len([c for c in companies if c.careers_url])
    companies_with_no_data = len([c for c in companies if not c.website])

    logger.info("=" * 60)
    logger.info("PIPELINE RUN SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Companies found:       {len(companies)}")
    logger.info(f"  Websites resolved:     {websites_resolved}/{len(companies)}")
    logger.info(f"  Careers pages found:   {careers_found}/{len(companies)}")
    logger.info(f"  Companies with jobs:   {companies_with_jobs}/{len(companies)}")
    logger.info(f"  Total tech roles:      {total_jobs}")
    logger.info(f"  Unresolved companies:  {companies_with_no_data}")
    logger.info(f"  ---")
    logger.info(f"  Stage 1 (RSS):         {stage1_time:.1f}s")
    logger.info(f"  Stage 2 (Resolve):     {stage2_time:.1f}s")
    logger.info(f"  Stage 3 (Jobs):        {stage3_time:.1f}s")
    logger.info(f"  Total pipeline time:   {pipeline_time:.1f}s")
    logger.info("=" * 60)

    # Per-company breakdown
    logger.info("PER-COMPANY BREAKDOWN:")
    for c in companies:
        logger.info(
            f"  {c.name:30s} | website={'yes' if c.website else 'NO ':3s} "
            f"| resolved_via={c.resolution_method or 'none':20s} "
            f"| careers={'yes' if c.careers_url else 'NO ':3s} "
            f"| scraper={c.scraper_used or 'none':25s} "
            f"| jobs={len(c.jobs)}"
            + (f" | {c.funding_amount}" if c.funding_amount else "")
        )
    logger.info("=" * 60)
    logger.info("Done.")


if __name__ == "__main__":
    run()

import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = Path(__file__).parent / "templates"


def render_digest(companies: list, date_str: str) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("digest.html")

    total_jobs = sum(len(c.jobs) for c in companies)

    return template.render(
        companies=companies,
        date_str=date_str,
        total_companies=len(companies),
        total_jobs=total_jobs,
    )


def render_plain_text(companies: list, date_str: str) -> str:
    lines = [
        f"PARADE DIGEST — {date_str}",
        f"{len(companies)} newly funded companies",
        "=" * 60,
        "",
    ]

    for company in companies:
        funding_info = " | ".join(filter(None, [company.funding_amount, company.funding_round]))
        lines.append(f"{company.name}" + (f"  [{funding_info}]" if funding_info else ""))

        if company.description:
            lines.append(company.description)

        if company.source_url:
            lines.append(f"Source: {company.source_url}")

        if company.jobs:
            lines.append("Open Tech Roles:")
            for job in company.jobs:
                lines.append(f"  • [{job.department}] {job.title} — {job.location}")
                lines.append(f"    {job.url}")
        else:
            lines.append("No tech roles found.")

        lines.append("")
        lines.append("-" * 60)
        lines.append("")

    return "\n".join(lines)

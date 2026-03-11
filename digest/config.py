import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    GMAIL_USER: str = os.environ["GMAIL_USER"]
    GMAIL_APP_PASSWORD: str = os.environ["GMAIL_APP_PASSWORD"]
    RECIPIENT_EMAIL: str = os.environ["RECIPIENT_EMAIL"]

    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "10"))
    MAX_COMPANIES: int = int(os.getenv("MAX_COMPANIES", "15"))
    MAX_JOBS_PER_CO: int = int(os.getenv("MAX_JOBS_PER_CO", "5"))
    LOOKBACK_HOURS: int = int(os.getenv("LOOKBACK_HOURS", "24"))

    RSS_FEEDS: list = [
        "https://techcrunch.com/category/funding/feed/",
        "https://news.crunchbase.com/feed/",
        "https://venturebeat.com/feed/",
    ]

    TECH_KEYWORDS: list = [
        "engineer", "engineering", "developer", "software",
        "data", "machine learning", "ml", "ai", "llm",
        "product manager", "devops", "infrastructure", "platform",
        "security", "backend", "frontend", "fullstack", "full-stack",
        "analytics", "scientist", "sre", "cloud", "architect",
    ]

    EXCLUDE_KEYWORDS: list = [
        "sales engineer", "account executive", "recruiter",
        "office manager", "hr ", "human resources",
    ]

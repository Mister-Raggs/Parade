from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JobListing:
    title: str
    location: str
    url: str
    department: str


@dataclass
class FundedCompany:
    name: str
    source_url: str
    funding_amount: Optional[str] = None
    funding_round: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    careers_url: Optional[str] = None
    jobs: list = field(default_factory=list)

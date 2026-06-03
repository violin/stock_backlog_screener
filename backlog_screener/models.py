from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FilingScan:
    form: str = ""
    filing_date: str = ""
    url: str = ""
    backlog_mentions: int = 0
    rpo_mentions: int = 0
    snippets: List[str] = field(default_factory=list)
    warning: str = ""


@dataclass
class CandidateMetrics:
    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: Optional[float] = None
    institutional_ownership: Optional[float] = None
    insider_ownership: Optional[float] = None
    quarterly_revenue_yoy: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    price: Optional[float] = None
    backlog_mentions: int = 0
    rpo_mentions: int = 0
    filing_form: str = ""
    filing_date: str = ""
    filing_url: str = ""
    backlog_snippets: List[str] = field(default_factory=list)
    source: str = "yfinance"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenResult:
    metrics: CandidateMetrics
    score: float
    passed: bool
    financial_passed: bool
    hard_pass_count: int
    hard_failures: List[str] = field(default_factory=list)
    positives: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

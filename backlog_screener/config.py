from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class ScreenThresholds:
    min_market_cap: float = 500_000_000
    max_market_cap: float = 4_000_000_000
    min_institutional_ownership: float = 0.65
    min_insider_ownership: float = 0.05
    min_quarterly_revenue_yoy: float = 0.25
    max_trailing_pe: float = 30.0


@dataclass(frozen=True)
class BacklogScanConfig:
    forms: Tuple[str, ...] = ("10-Q", "10-K")
    terms: Tuple[str, ...] = field(
        default_factory=lambda: (
            "backlog",
            "remaining performance obligation",
            "remaining performance obligations",
            "contract liability",
            "contract liabilities",
            "deferred revenue",
            "RPO",
        )
    )
    snippet_radius: int = 220
    max_snippets: int = 4


DEFAULT_EXCHANGES = ("NMS", "NYQ", "ASE", "NCM", "NGM")

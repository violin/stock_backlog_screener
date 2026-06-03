from .models import CandidateMetrics


def sample_metrics():
    return [
        CandidateMetrics(
            ticker="DEMO",
            name="Demo Infrastructure Services",
            sector="Industrials",
            industry="Engineering & Construction",
            market_cap=1_800_000_000,
            institutional_ownership=0.72,
            insider_ownership=0.08,
            quarterly_revenue_yoy=0.34,
            trailing_pe=22.4,
            backlog_mentions=8,
            rpo_mentions=2,
            filing_form="10-Q",
            filing_date="2026-05-01",
            filing_url="https://www.sec.gov/",
            backlog_snippets=["Demo filing text mentions backlog growth and remaining performance obligations."],
        ),
        CandidateMetrics(
            ticker="BIG",
            name="Large Obvious Mega Cap",
            sector="Technology",
            industry="Semiconductors",
            market_cap=420_000_000_000,
            institutional_ownership=0.68,
            insider_ownership=0.01,
            quarterly_revenue_yoy=0.29,
            trailing_pe=44.0,
        ),
    ]

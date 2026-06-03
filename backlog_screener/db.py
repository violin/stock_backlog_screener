from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from .datasources import DATA_SOURCE_DEFINITIONS, source_payload
from .settings import PROJECT_ROOT


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def stable_hash(*parts: Any) -> str:
    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            payload = part
        else:
            payload = str(part).encode("utf-8", errors="ignore")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PostgresStore:
    def __init__(self, dsn: str):
        import psycopg
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self._dict_row = dict_row
        self.dsn = dsn

    def connect(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def ensure_schema(self, schema_path: str | Path | None = None) -> None:
        path = Path(schema_path) if schema_path else PROJECT_ROOT / "schema" / "postgres.sql"
        sql = path.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.execute(sql)
            conn.commit()
        self.seed_sources()

    def seed_sources(self) -> None:
        source_policies = _load_rate_limit_source_policies()
        sources = [
            source_payload(source, source_policies.get(source.source_key))
            for source in DATA_SOURCE_DEFINITIONS
        ]
        with self.connect() as conn:
            for source in sources:
                conn.execute(
                    """
                    insert into data_sources
                        (source_key, source_name, source_type, trust_level, rate_limit_policy, enabled, metadata)
                    values (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                    on conflict (source_key) do update set
                        source_name = excluded.source_name,
                        source_type = excluded.source_type,
                        trust_level = excluded.trust_level,
                        rate_limit_policy = excluded.rate_limit_policy,
                        enabled = excluded.enabled,
                        metadata = excluded.metadata,
                        updated_at = now()
                    """,
                    (
                        source["source_key"],
                        source["source_name"],
                        source["source_type"],
                        source["trust_level"],
                        json_dumps(source["rate_limit_policy"]),
                        source["enabled"],
                        json_dumps(source["metadata"]),
                    ),
                )
            conn.commit()

    def data_sources(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select *
                from data_sources
                order by
                    coalesce(metadata->>'collection_scope', ''),
                    source_key
                """
            ).fetchall()
            return list(rows)

    def start_run(self, *, tickers: list[str], trigger: str, config: dict[str, Any]) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                insert into collection_runs (trigger, status, tickers, config)
                values (%s, 'RUNNING', %s, %s::jsonb)
                returning id
                """,
                (trigger, tickers, json_dumps(config)),
            ).fetchone()
            conn.commit()
            return int(row["id"])

    def finish_run(self, run_id: int, *, status: str, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update collection_runs
                set status = %s,
                    error_message = %s,
                    finished_at = now()
                where id = %s
                """,
                (status, error, run_id),
            )
            conn.commit()

    def upsert_company(
        self,
        ticker: str,
        *,
        name: str = "",
        market: str = "US",
        futu_code: str | None = None,
        sector: str = "",
        industry: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into companies (ticker, market, futu_code, name, sector, industry, metadata)
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict (ticker) do update set
                    market = excluded.market,
                    futu_code = coalesce(excluded.futu_code, companies.futu_code),
                    name = case when excluded.name <> '' then excluded.name else companies.name end,
                    sector = case when excluded.sector <> '' then excluded.sector else companies.sector end,
                    industry = case when excluded.industry <> '' then excluded.industry else companies.industry end,
                    metadata = companies.metadata || excluded.metadata,
                    updated_at = now()
                """,
                (
                    ticker.upper(),
                    market,
                    futu_code,
                    name or "",
                    sector or "",
                    industry or "",
                    json_dumps(metadata or {}),
                ),
            )
            conn.commit()

    def save_observation(
        self,
        *,
        run_id: int | None,
        ticker: str,
        source_key: str,
        source_type: str,
        observation_type: str,
        title: str = "",
        source_url: str = "",
        source_published_at: datetime | date | str | None = None,
        raw_text: str = "",
        raw_json: dict[str, Any] | None = None,
        trust_level: int = 50,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        raw_hash = stable_hash(ticker.upper(), source_key, observation_type, raw_text, json_dumps(raw_json or {}))
        with self.connect() as conn:
            row = conn.execute(
                """
                insert into raw_observations (
                    run_id, ticker, source_key, source_type, observation_type, title, source_url,
                    source_published_at, raw_text, raw_json, raw_hash, trust_level, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                on conflict (ticker, source_key, observation_type, raw_hash)
                do update set
                    run_id = excluded.run_id,
                    fetched_at = now(),
                    metadata = raw_observations.metadata || excluded.metadata
                returning id
                """,
                (
                    run_id,
                    ticker.upper(),
                    source_key,
                    source_type,
                    observation_type,
                    title,
                    source_url,
                    source_published_at,
                    raw_text,
                    json_dumps(raw_json or {}),
                    raw_hash,
                    trust_level,
                    json_dumps(metadata or {}),
                ),
            ).fetchone()
            conn.commit()
            return int(row["id"])

    def save_information_item(
        self,
        *,
        run_id: int | None,
        observation_id: int | None,
        ticker: str,
        dimension: str,
        title: str,
        summary: str = "",
        raw_excerpt: str = "",
        event_date: datetime | date | str | None = None,
        source_key: str,
        source_url: str = "",
        importance_score: float = 0,
        quality_score: float = 0,
        sentiment_score: float = 0,
        confidence_score: float = 0,
        time_weight: float = 1,
        extracted_by: str = "heuristic",
        evidence: dict[str, Any] | None = None,
    ) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                insert into information_items (
                    run_id, observation_id, ticker, dimension, event_date, title, summary,
                    raw_excerpt, source_key, source_url, importance_score, quality_score,
                    sentiment_score, confidence_score, time_weight, extracted_by, evidence
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                (
                    run_id,
                    observation_id,
                    ticker.upper(),
                    dimension,
                    event_date,
                    title,
                    summary,
                    raw_excerpt,
                    source_key,
                    source_url,
                    importance_score,
                    quality_score,
                    sentiment_score,
                    confidence_score,
                    time_weight,
                    extracted_by,
                    json_dumps(evidence or {}),
                ),
            ).fetchone()
            conn.commit()
            return int(row["id"])

    def latest_information_items(self, ticker: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select *
                from information_items
                where ticker = %s
                order by event_date desc nulls last, created_at desc
                limit %s
                """,
                (ticker.upper(), limit),
            ).fetchall()
            return list(rows)

    def company(self, ticker: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select *
                from companies
                where ticker = %s
                """,
                (ticker.upper(),),
            ).fetchone()
            return dict(row) if row else None

    def latest_score(self, ticker: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select
                    s.*,
                    c.name,
                    c.sector,
                    c.industry,
                    coalesce(nullif(c.industry, ''), nullif(c.sector, ''), 'Unclassified') as sector_group
                from security_scores s
                join companies c on c.ticker = s.ticker
                where s.ticker = %s
                order by s.scored_at desc
                limit 1
                """,
                (ticker.upper(),),
            ).fetchone()
            return dict(row) if row else None

    def latest_company_summary(self, ticker: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select *
                from information_items
                where ticker = %s
                  and dimension = 'company_summary'
                order by created_at desc
                limit 1
                """,
                (ticker.upper(),),
            ).fetchone()
            return dict(row) if row else None

    def save_score(
        self,
        *,
        run_id: int | None,
        ticker: str,
        total_score: float,
        grade: str,
        component_scores: dict[str, Any],
        explanation: str,
        missing_dimensions: Iterable[str],
        model_version: str = "hidden_champion_v3",
    ) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                insert into security_scores (
                    run_id, ticker, total_score, grade, component_scores,
                    explanation, missing_dimensions, model_version
                )
                values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                on conflict (run_id, ticker, model_version) do update set
                    scored_at = now(),
                    total_score = excluded.total_score,
                    grade = excluded.grade,
                    component_scores = excluded.component_scores,
                    explanation = excluded.explanation,
                    missing_dimensions = excluded.missing_dimensions
                returning id
                """,
                (
                    run_id,
                    ticker.upper(),
                    total_score,
                    grade,
                    json_dumps(component_scores),
                    explanation,
                    list(missing_dimensions),
                    model_version,
                ),
            ).fetchone()
            conn.commit()
            return int(row["id"])

    def ranked_scores(
        self,
        *,
        min_score: float = 0,
        limit: int = 100,
        query: str = "",
        sector: str = "",
    ) -> list[dict[str, Any]]:
        search = _search_pattern(query)
        clean_sector = str(sector or "").strip()
        with self.connect() as conn:
            rows = conn.execute(
                """
                with latest as (
                    select distinct on (s.ticker)
                        s.*,
                        c.name,
                        c.futu_code,
                        c.sector,
                        c.industry,
                        coalesce(nullif(c.industry, ''), nullif(c.sector, ''), 'Unclassified') as sector_group
                    from security_scores s
                    join companies c on c.ticker = s.ticker
                    order by s.ticker, s.scored_at desc
                )
                select *
                from latest
                where total_score >= %s
                  and (%s = '' or sector_group = %s)
                  and (
                    %s = ''
                    or ticker ilike %s
                    or coalesce(futu_code, '') ilike %s
                    or name ilike %s
                    or sector ilike %s
                    or industry ilike %s
                  )
                order by total_score desc, scored_at desc
                limit %s
                """,
                (min_score, clean_sector, clean_sector, query.strip(), search, search, search, search, search, limit),
            ).fetchall()
            return list(rows)

    def ranked_scores_by_sector(
        self,
        *,
        min_score: float = 0,
        per_sector: int = 5,
        query: str = "",
        sector: str = "",
    ) -> list[dict[str, Any]]:
        per_sector = max(1, min(10, int(per_sector)))
        search = _search_pattern(query)
        clean_sector = str(sector or "").strip()
        with self.connect() as conn:
            rows = conn.execute(
                """
                with latest as (
                    select distinct on (s.ticker)
                        s.*,
                        c.name,
                        c.futu_code,
                        c.sector,
                        c.industry,
                        coalesce(nullif(c.industry, ''), nullif(c.sector, ''), 'Unclassified') as sector_group
                    from security_scores s
                    join companies c on c.ticker = s.ticker
                    order by s.ticker, s.scored_at desc
                ),
                ranked as (
                    select
                        latest.*,
                        row_number() over (
                            partition by sector_group
                            order by total_score desc, scored_at desc
                        ) as sector_rank
                    from latest
                    where total_score >= %s
                      and (%s = '' or sector_group = %s)
                      and (
                        %s = ''
                        or ticker ilike %s
                        or coalesce(futu_code, '') ilike %s
                        or name ilike %s
                        or sector ilike %s
                        or industry ilike %s
                      )
                )
                select *
                from ranked
                where %s <> '' or sector_rank <= %s
                order by sector_group asc, sector_rank asc
                """,
                (
                    min_score,
                    clean_sector,
                    clean_sector,
                    query.strip(),
                    search,
                    search,
                    search,
                    search,
                    search,
                    query.strip(),
                    per_sector,
                ),
            ).fetchall()
            return list(rows)

    def ranked_sectors(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                with latest as (
                    select distinct on (s.ticker)
                        s.ticker,
                        s.total_score,
                        coalesce(nullif(c.industry, ''), nullif(c.sector, ''), 'Unclassified') as sector_group
                    from security_scores s
                    join companies c on c.ticker = s.ticker
                    order by s.ticker, s.scored_at desc
                )
                select
                    sector_group as sector,
                    count(*) as candidate_count,
                    max(total_score) as best_score
                from latest
                group by sector_group
                order by best_score desc nulls last, sector_group asc
                """
            ).fetchall()
            return list(rows)

    def watch_ticker(self, ticker: str, *, note: str = "") -> dict[str, Any] | None:
        clean_ticker = ticker.upper()
        self.upsert_company(clean_ticker)
        with self.connect() as conn:
            conn.execute(
                """
                insert into watched_tickers (ticker, note)
                values (%s, %s)
                on conflict (ticker) do update set
                    note = excluded.note,
                    updated_at = now()
                """,
                (clean_ticker, note),
            )
            conn.commit()
        return self.watched_ticker(clean_ticker)

    def unwatch_ticker(self, ticker: str) -> None:
        with self.connect() as conn:
            conn.execute("delete from watched_tickers where ticker = %s", (ticker.upper(),))
            conn.commit()

    def watched_ticker(self, ticker: str) -> dict[str, Any] | None:
        rows = self.watched_tickers()
        for row in rows:
            if row.get("ticker") == ticker.upper():
                return row
        return None

    def watched_tickers(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                with latest_scores as (
                    select distinct on (s.ticker) s.*
                    from security_scores s
                    order by s.ticker, s.scored_at desc
                )
                select
                    w.ticker,
                    w.note,
                    w.created_at as watched_at,
                    c.name,
                    c.futu_code,
                    c.sector,
                    c.industry,
                    coalesce(nullif(c.industry, ''), nullif(c.sector, ''), 'Unclassified') as sector_group,
                    s.total_score,
                    s.grade,
                    s.component_scores,
                    s.missing_dimensions,
                    s.scored_at,
                    s.run_id
                from watched_tickers w
                join companies c on c.ticker = w.ticker
                left join latest_scores s on s.ticker = w.ticker
                order by w.created_at desc, w.ticker asc
                """
            ).fetchall()
            return list(rows)

    def future_events(self, ticker: str, *, limit: int = 80) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select *
                from future_events
                where ticker = %s
                order by event_date asc nulls last, importance_score desc, created_at desc
                limit %s
                """,
                (ticker.upper(), limit),
            ).fetchall()
            return list(rows)

    def latest_ticker_run(self, ticker: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select
                    id,
                    trigger,
                    status,
                    tickers,
                    config,
                    started_at,
                    finished_at,
                    error_message
                from collection_runs
                where %s = any(tickers)
                order by coalesce(finished_at, started_at) desc, id desc
                limit 1
                """,
                (ticker.upper(),),
            ).fetchone()
            return dict(row) if row else None

    def search_ranked_scores(self, *, query: str, limit: int = 50) -> list[dict[str, Any]]:
        clean_query = query.strip()
        if not clean_query:
            return []
        limit = max(1, min(100, int(limit)))
        escaped = escape_like(clean_query)
        pattern = f"%{escaped}%"
        prefix_pattern = f"{escaped}%"
        exact_ticker = clean_query.upper()
        with self.connect() as conn:
            rows = conn.execute(
                """
                with latest as (
                    select distinct on (s.ticker)
                        s.*,
                        c.name,
                        c.futu_code,
                        c.sector,
                        c.industry,
                        coalesce(nullif(c.industry, ''), nullif(c.sector, ''), 'Unclassified') as sector_group
                    from security_scores s
                    join companies c on c.ticker = s.ticker
                    order by s.ticker, s.scored_at desc
                ),
                ranked as (
                    select
                        latest.*,
                        row_number() over (
                            partition by sector_group
                            order by total_score desc, scored_at desc
                        ) as sector_rank
                    from latest
                )
                select *
                from ranked
                where ticker ilike %s escape '\\'
                   or coalesce(futu_code, '') ilike %s escape '\\'
                   or coalesce(name, '') ilike %s escape '\\'
                order by
                    case
                        when upper(ticker) = %s then 0
                        when ticker ilike %s escape '\\' then 1
                        when coalesce(futu_code, '') ilike %s escape '\\' then 2
                        when coalesce(name, '') ilike %s escape '\\' then 3
                        else 4
                    end,
                    total_score desc,
                    scored_at desc
                limit %s
                """,
                (
                    pattern,
                    pattern,
                    pattern,
                    exact_ticker,
                    prefix_pattern,
                    prefix_pattern,
                    prefix_pattern,
                    limit,
                ),
            ).fetchall()
            return list(rows)

    def timeline(
        self,
        ticker: str,
        *,
        dimension: str | None = None,
        min_importance: float = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [ticker.upper(), min_importance]
        where = "ticker = %s and importance_score >= %s"
        if dimension:
            where += " and dimension = %s"
            params.append(dimension)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                with deduped as (
                    select distinct on (
                        dimension,
                        source_key,
                        title,
                        event_date,
                        coalesce(source_url, '')
                    ) *
                    from information_items
                    where {where}
                    order by
                        dimension,
                        source_key,
                        title,
                        event_date,
                        coalesce(source_url, ''),
                        created_at desc,
                        importance_score desc
                )
                select *
                from deduped
                order by event_date desc nulls last, created_at desc, importance_score desc
                limit %s
                """,
                params,
            ).fetchall()
            return list(rows)

    def runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    select *
                    from collection_runs
                    order by started_at desc
                    limit %s
                    """,
                    (limit,),
                ).fetchall()
            )


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _search_pattern(query: str) -> str:
    cleaned = str(query or "").strip().upper()
    return f"%{cleaned}%"


def _load_rate_limit_source_policies() -> dict[str, dict[str, Any]]:
    path = PROJECT_ROOT / "configs" / "rate_limits.json"
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    policies: dict[str, dict[str, Any]] = {}
    for source_key, source in (config.get("sources") or {}).items():
        policies[source_key] = {
            "version": config.get("version"),
            "updated_at": config.get("updated_at"),
            "source_type": source.get("source_type"),
            "observed_limit": source.get("observed_limit"),
            "interfaces": source.get("interfaces", {}),
            "notes": source.get("notes", []),
        }
    return policies

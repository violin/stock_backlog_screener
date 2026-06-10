create table if not exists companies (
    ticker text primary key,
    market text not null default 'US',
    futu_code text,
    name text not null default '',
    sector text not null default '',
    industry text not null default '',
    status text not null default 'ACTIVE',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists data_sources (
    source_key text primary key,
    source_name text not null,
    source_type text not null,
    trust_level integer not null default 50,
    rate_limit_policy jsonb not null default '{}'::jsonb,
    enabled boolean not null default true,
    metadata jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists collection_runs (
    id bigserial primary key,
    trigger text not null default 'manual',
    status text not null default 'RUNNING',
    tickers text[] not null default array[]::text[],
    config jsonb not null default '{}'::jsonb,
    error_message text,
    started_at timestamptz not null default now(),
    finished_at timestamptz
);

create table if not exists raw_observations (
    id bigserial primary key,
    run_id bigint references collection_runs(id) on delete set null,
    ticker text not null references companies(ticker) on delete cascade,
    source_key text not null references data_sources(source_key),
    source_type text not null,
    observation_type text not null,
    title text not null default '',
    source_url text not null default '',
    source_published_at timestamptz,
    fetched_at timestamptz not null default now(),
    raw_text text not null default '',
    raw_json jsonb not null default '{}'::jsonb,
    raw_hash text not null,
    trust_level integer not null default 50,
    metadata jsonb not null default '{}'::jsonb,
    unique (ticker, source_key, observation_type, raw_hash)
);

create index if not exists idx_raw_observations_ticker_fetched
    on raw_observations (ticker, fetched_at desc);

create table if not exists information_items (
    id bigserial primary key,
    run_id bigint references collection_runs(id) on delete set null,
    observation_id bigint references raw_observations(id) on delete cascade,
    ticker text not null references companies(ticker) on delete cascade,
    dimension text not null,
    event_date timestamptz,
    title text not null,
    summary text not null default '',
    raw_excerpt text not null default '',
    source_key text not null,
    source_url text not null default '',
    importance_score numeric(6, 2) not null default 0,
    quality_score numeric(6, 2) not null default 0,
    sentiment_score numeric(6, 2) not null default 0,
    confidence_score numeric(6, 2) not null default 0,
    time_weight numeric(6, 2) not null default 1,
    extracted_by text not null default 'heuristic',
    evidence jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_information_items_ticker_event
    on information_items (ticker, event_date desc nulls last, created_at desc);

create index if not exists idx_information_items_dimension_importance
    on information_items (dimension, importance_score desc);

create table if not exists security_scores (
    id bigserial primary key,
    run_id bigint references collection_runs(id) on delete set null,
    ticker text not null references companies(ticker) on delete cascade,
    scored_at timestamptz not null default now(),
    total_score numeric(6, 2) not null,
    grade text not null,
    component_scores jsonb not null default '{}'::jsonb,
    explanation text not null default '',
    missing_dimensions text[] not null default array[]::text[],
    model_version text not null default 'hidden_champion_v3',
    unique (run_id, ticker, model_version)
);

create index if not exists idx_security_scores_latest
    on security_scores (ticker, scored_at desc);

create index if not exists idx_security_scores_rank
    on security_scores (total_score desc, scored_at desc);

create table if not exists watched_tickers (
    ticker text primary key references companies(ticker) on delete cascade,
    note text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_watched_tickers_created
    on watched_tickers (created_at desc);

create table if not exists future_events (
    id bigserial primary key,
    ticker text not null references companies(ticker) on delete cascade,
    event_date date,
    window_label text not null default '',
    catalyst_type text not null default '',
    title text not null,
    summary text not null default '',
    source_key text not null default '',
    source_url text not null default '',
    importance_score numeric(6, 2) not null default 0,
    confidence_score numeric(6, 2) not null default 0,
    status text not null default 'WATCH',
    evidence jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_future_events_ticker_date
    on future_events (ticker, event_date asc nulls last, importance_score desc);

create table if not exists opening_radar_reports (
    id bigserial primary key,
    report_date date not null,
    session_label text not null default 'pre_open',
    snapshot jsonb not null default '{}'::jsonb,
    advice jsonb not null default '{}'::jsonb,
    provider text not null default '',
    prompt text not null default '',
    raw_response text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (report_date, session_label)
);

create index if not exists idx_opening_radar_reports_updated
    on opening_radar_reports (updated_at desc);

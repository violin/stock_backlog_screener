let selectedTicker = null;
let selectedTickerWatched = false;
let activeDetailTab = "summary";
let activePool = "all";
let candidateSearchTimer = null;
let candidateRefreshRequest = 0;
let sectorsLoaded = false;
let datasourcesLoaded = false;
let activeWorkspaceView = "research";
let latestWatchlist = new Set();
let tradingViewLoadedTicker = null;
let openingRadarLoaded = false;
let openingRadarSnapshot = null;
let openingRadarReportId = null;
let activeSectorRadar = "space";

const TICKER_STORAGE_KEY = "codeBeta.tickers";
const LEGACY_TICKER_STORAGE_KEY = "hiddenChampionScreener.tickers";
const CANDIDATE_SEARCH_DEBOUNCE_MS = 250;

const els = {
  openScreeningButton: document.querySelector("#openScreeningButton"),
  navPoolsButton: document.querySelector("#navPoolsButton"),
  navDetailsButton: document.querySelector("#navDetailsButton"),
  navOpeningRadarButton: document.querySelector("#navOpeningRadarButton"),
  navDataSourcesButton: document.querySelector("#navDataSourcesButton"),
  openRunsButton: document.querySelector("#openRunsButton"),
  globalSearch: document.querySelector("#globalSearch"),
  screeningDialog: document.querySelector("#screeningDialog"),
  closeScreeningDialog: document.querySelector("#closeScreeningDialog"),
  screenMode: document.querySelector("#screenMode"),
  screenCondition: document.querySelector("#screenCondition"),
  useFutuScreen: document.querySelector("#useFutuScreen"),
  useSec: document.querySelector("#useSec"),
  researchGrid: document.querySelector("#researchGrid"),
  datasourcePage: document.querySelector("#datasourcePage"),
  openingRadarPage: document.querySelector("#openingRadarPage"),
  openingRadarAsOf: document.querySelector("#openingRadarAsOf"),
  refreshOpeningRadarButton: document.querySelector("#refreshOpeningRadarButton"),
  generateOpeningAdviceButton: document.querySelector("#generateOpeningAdviceButton"),
  openingRadarPrimary: document.querySelector("#openingRadarPrimary"),
  sectorRadarTabs: document.querySelector("#sectorRadarTabs"),
  sectorRadarPanel: document.querySelector("#sectorRadarPanel"),
  openingAdviceMeta: document.querySelector("#openingAdviceMeta"),
  openingReportHistory: document.querySelector("#openingReportHistory"),
  openingAdviceBody: document.querySelector("#openingAdviceBody"),
  datasourceSummary: document.querySelector("#datasourceSummary"),
  datasourceList: document.querySelector("#datasourceList"),
  candidatePoolList: document.querySelector("#candidatePoolList"),
  candidatePanelTitle: document.querySelector("#candidatePanelTitle"),
  candidateList: document.querySelector("#candidateList"),
  candidateCount: document.querySelector("#candidateCount"),
  detailTitle: document.querySelector("#detailTitle"),
  detailScore: document.querySelector("#detailScore"),
  detailLastRun: document.querySelector("#detailLastRun"),
  detailWatchButton: document.querySelector("#detailWatchButton"),
  rerunTickerButton: document.querySelector("#rerunTickerButton"),
  summaryTab: document.querySelector("#summaryTab"),
  truthTab: document.querySelector("#truthTab"),
  timetableTab: document.querySelector("#timetableTab"),
  chartTab: document.querySelector("#chartTab"),
  summaryPanel: document.querySelector("#summaryPanel"),
  truthPanel: document.querySelector("#truthPanel"),
  timetablePanel: document.querySelector("#timetablePanel"),
  chartPanel: document.querySelector("#chartPanel"),
  tradingViewWidget: document.querySelector("#tradingViewWidget"),
  tradingViewLink: document.querySelector("#tradingViewLink"),
  summaryMeta: document.querySelector("#summaryMeta"),
  summaryBody: document.querySelector("#summaryBody"),
  summaryButton: document.querySelector("#summaryButton"),
  trendReturn: document.querySelector("#trendReturn"),
  trendChartBody: document.querySelector("#trendChartBody"),
  trendRange: document.querySelector("#trendRange"),
  trendPrice: document.querySelector("#trendPrice"),
  missingData: document.querySelector("#missingData"),
  scoreBreakdown: document.querySelector("#scoreBreakdown"),
  timeline: document.querySelector("#timeline"),
  timetableStatus: document.querySelector("#timetableStatus"),
  refreshTimetableButton: document.querySelector("#refreshTimetableButton"),
  futureTimeline: document.querySelector("#futureTimeline"),
  workerState: document.querySelector("#workerState"),
  latestRun: document.querySelector("#latestRun"),
  queueDrawer: document.querySelector("#queueDrawer"),
  queueClose: document.querySelector("#queueClose"),
  queueProgress: document.querySelector("#queueProgress"),
  queueStage: document.querySelector("#queueStage"),
  monitorSummary: document.querySelector("#monitorSummary"),
  activeRunList: document.querySelector("#activeRunList"),
  recentRunList: document.querySelector("#recentRunList"),
  recentRunCount: document.querySelector("#recentRunCount"),
  queueCurrent: document.querySelector("#queueCurrent"),
  queuePending: document.querySelector("#queuePending"),
  queueCompleted: document.querySelector("#queueCompleted"),
  queueFailed: document.querySelector("#queueFailed"),
  queueCurrentCount: document.querySelector("#queueCurrentCount"),
  queuePendingCount: document.querySelector("#queuePendingCount"),
  queueCompletedCount: document.querySelector("#queueCompletedCount"),
  queueFailedCount: document.querySelector("#queueFailedCount"),
  tickerInput: document.querySelector("#tickerInput"),
  candidateSearch: document.querySelector("#candidateSearch"),
  sectorFilter: document.querySelector("#sectorFilter"),
  minScore: document.querySelector("#minScore"),
  perSector: document.querySelector("#perSector"),
  dimensionFilter: document.querySelector("#dimensionFilter"),
  useYfinance: document.querySelector("#useYfinance"),
  use13f: document.querySelector("#use13f"),
  useUsaspending: document.querySelector("#useUsaspending"),
  useLaunchLibrary: document.querySelector("#useLaunchLibrary"),
  useCompanyOfficial: document.querySelector("#useCompanyOfficial"),
  useOpenInsider: document.querySelector("#useOpenInsider"),
  useMinimax: document.querySelector("#useMinimax"),
  runButton: document.querySelector("#runButton"),
  refreshButton: document.querySelector("#refreshButton"),
};

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

async function refreshAll() {
  const requestId = ++candidateRefreshRequest;
  await Promise.all([refreshRuns(), refreshWatchlist(), loadSectors()]);
  const searchTerm = els.candidateSearch.value.trim();
  const isSearching = Boolean(searchTerm);
  const minScore = Number(els.minScore.value || 0);
  const perSector = Number(els.perSector.value || 5);
  const sector = els.sectorFilter.value || "";
  setCandidateSearchMode(isSearching);
  const params = new URLSearchParams({
    min_score: String(isSearching ? 0 : minScore),
    per_sector: String(perSector),
  });
  if (sector) params.set("sector", sector);
  if (isSearching) {
    params.set("query", searchTerm);
    params.set("q", searchTerm);
  }
  const payload = await api(`/api/candidates/grouped?${params.toString()}`);
  if (requestId !== candidateRefreshRequest) return;
  const normalizedGroups = normalizeCandidateGroups(payload.groups || [], searchTerm);
  const poolCounts = candidatePoolCounts(flattenGroups(normalizedGroups));
  renderCandidatePools(poolCounts);
  const groups = filterGroupsByPool(normalizedGroups, activePool);
  const candidates = flattenGroups(groups);
  const selectedKey = selectedTicker ? selectedTicker.toUpperCase() : "";
  const selectedInResults = selectedKey && candidates.some((item) => tickerKey(item) === selectedKey);
  const exactMatch = isSearching ? candidates.find((item) => tickerKey(item) === searchTerm.toUpperCase()) : null;
  if (exactMatch && selectedTicker !== exactMatch.ticker) {
    selectedTicker = exactMatch.ticker;
  } else if (!selectedInResults) {
    selectedTicker = candidates.length ? candidates[0].ticker : null;
  }
  renderCandidateGroups(groups, {
    emptyText: isSearching ? "No matching candidates" : "No candidates",
    searchTerm,
  });
  if (selectedTicker) {
    await loadTicker(selectedTicker);
  } else {
    clearTickerDetail();
  }
}

async function loadSectors() {
  if (sectorsLoaded) return;
  try {
    const data = await api("/api/sectors");
    const current = els.sectorFilter.value;
    els.sectorFilter.innerHTML = `<option value="">All Sectors</option>`;
    for (const item of data.sectors || []) {
      const option = document.createElement("option");
      option.value = item.sector || "";
      option.textContent = `${item.sector || "Unclassified"} (${Number(item.candidate_count || 0)})`;
      els.sectorFilter.appendChild(option);
    }
    els.sectorFilter.value = current;
    sectorsLoaded = true;
  } catch (error) {
    sectorsLoaded = true;
  }
}

async function refreshWatchlist() {
  try {
    const data = await api("/api/watchlist");
    latestWatchlist = new Set((data.tickers || []).map((item) => String(item.ticker || "").toUpperCase()));
  } catch (error) {
    latestWatchlist = new Set();
  }
}

async function showWorkspaceView(view) {
  activeWorkspaceView = view;
  const datasourceView = view === "datasources";
  const openingRadarView = view === "opening-radar";
  els.researchGrid.hidden = datasourceView || openingRadarView;
  els.datasourcePage.hidden = !datasourceView;
  els.openingRadarPage.hidden = !openingRadarView;
  els.openScreeningButton.classList.toggle("active", view === "screening");
  els.navOpeningRadarButton.classList.toggle("active", openingRadarView);
  els.navPoolsButton.classList.toggle("active", view === "research");
  els.navDetailsButton.classList.toggle("active", view === "details");
  els.navDataSourcesButton.classList.toggle("active", datasourceView);
  if (datasourceView) await loadDataSources();
  if (openingRadarView) await loadOpeningRadar();
}

async function loadOpeningRadar({force = false} = {}) {
  if (openingRadarLoaded && !force) return;
  els.openingRadarPrimary.innerHTML = `<div class="empty">Loading Nasdaq indicators</div>`;
  els.sectorRadarPanel.innerHTML = `<div class="empty">Loading sector indicators</div>`;
  try {
    const path = force ? "/api/opening-radar?force=1" : "/api/opening-radar";
    const data = await api(path);
    openingRadarSnapshot = data;
    openingRadarReportId = data.report?.id || null;
    openingRadarLoaded = true;
    renderOpeningRadar(data);
  } catch (error) {
    els.openingRadarPrimary.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    els.sectorRadarPanel.innerHTML = "";
  }
}

function renderOpeningRadar(data) {
  const report = data.report || {};
  els.openingRadarAsOf.textContent = report.report_date
    ? `Report ${report.report_date} · Updated ${formatShortTime(report.updated_at || data.as_of)}`
    : data.as_of
      ? `Updated ${formatShortTime(data.as_of)}`
      : "-";
  els.openingRadarPrimary.innerHTML = "";
  els.openingRadarPrimary.appendChild(renderRadarCard(data.primary, {fixed: true}));
  renderOpeningReportHistory(data.history || [], report.id);
  renderSectorRadarTabs(data.sectors || []);
  const active = (data.sectors || []).find((item) => item.key === activeSectorRadar) || (data.sectors || [])[0];
  els.sectorRadarPanel.innerHTML = "";
  if (active) {
    activeSectorRadar = active.key;
    els.sectorRadarPanel.appendChild(renderRadarCard(active));
  } else {
    els.sectorRadarPanel.innerHTML = `<div class="empty">No sector radar configured</div>`;
  }
  if (data.advice) {
    renderOpeningAdvice(data.advice_provider || report.provider, data.advice);
  } else {
    els.openingAdviceMeta.textContent = "Persisted after trigger";
    els.openingAdviceBody.innerHTML = `<div class="empty">No AI Prep saved for this report.</div>`;
  }
}

function renderOpeningReportHistory(history, activeId) {
  els.openingReportHistory.innerHTML = "";
  if (!history.length) {
    els.openingReportHistory.innerHTML = `<div class="history-empty">No reports</div>`;
    return;
  }
  for (const item of history) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-report-button${Number(item.id) === Number(activeId) ? " active" : ""}`;
    button.innerHTML = `
      <span>${escapeHtml(item.report_date || "-")}</span>
      <b>${item.has_advice ? "AI" : "Facts"}</b>
    `;
    button.addEventListener("click", () => loadOpeningRadarReport(item.id));
    els.openingReportHistory.appendChild(button);
  }
}

async function loadOpeningRadarReport(reportId) {
  els.openingRadarPrimary.innerHTML = `<div class="empty">Loading report</div>`;
  try {
    const data = await api(`/api/opening-radar/${reportId}`);
    openingRadarSnapshot = data;
    openingRadarReportId = data.report?.id || null;
    openingRadarLoaded = true;
    renderOpeningRadar(data);
  } catch (error) {
    els.openingRadarPrimary.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderSectorRadarTabs(sectors) {
  els.sectorRadarTabs.innerHTML = "";
  for (const sector of sectors) {
    const button = document.createElement("button");
    button.id = `sectorRadarTab-${sector.key}`;
    button.className = `detail-tab${sector.key === activeSectorRadar ? " active" : ""}`;
    button.type = "button";
    button.textContent = `${sector.label || sector.key} · ${sector.symbol || ""}`;
    button.addEventListener("click", () => {
      activeSectorRadar = sector.key;
      renderOpeningRadar(openingRadarSnapshot);
    });
    els.sectorRadarTabs.appendChild(button);
  }
}

function renderRadarCard(item, {fixed = false} = {}) {
  const article = document.createElement("article");
  article.className = `radar-card${fixed ? " fixed" : ""}`;
  if (!item || item.error) {
    article.innerHTML = `
      <div class="radar-card-head">
        <div><strong>${escapeHtml(item?.label || "Radar")}</strong><span>${escapeHtml(item?.symbol || "-")}</span></div>
        <mark>Data gap</mark>
      </div>
      <div class="empty">${escapeHtml(item?.error || "No radar data")}</div>
    `;
    return article;
  }
  const indicators = item.indicators || {};
  const metrics = [
    ["Regime", item.regime, item.directional_bias],
    ["MACD", numberText(indicators.macd_hist), `prev ${numberText(indicators.macd_hist_prev)}`],
    ["RSI", numberText(indicators.rsi14), rsiLabel(indicators.rsi14)],
    ["KDJ", `${numberText(indicators.kdj_k)}/${numberText(indicators.kdj_d)}/${numberText(indicators.kdj_j)}`, kdjLabel(indicators)],
    ["MA Stack", `${numberText(indicators.distance_ma20_pct)}%`, "vs MA20"],
    ["ADX", numberText(indicators.adx14), adxLabel(indicators.adx14)],
    ["ATR", `${numberText(indicators.atr14_pct)}%`, "14D range risk"],
    ["Vol", volatilityText(item), "IV / realized"],
  ];
  article.innerHTML = `
    <div class="radar-card-head">
      <div>
        <strong>${escapeHtml(item.label || item.key)}</strong>
        <span>${escapeHtml(item.symbol || "")} · ${escapeHtml(item.latest_date || "")} · close ${numberText(item.latest_close)}</span>
      </div>
      <mark data-regime="${escapeAttribute(item.regime)}">${escapeHtml(item.regime || "Unknown")}</mark>
    </div>
    <div class="radar-metric-grid">
      ${metrics
        .map(
          ([label, value, help]) => `
            <div class="radar-metric">
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
              <small>${escapeHtml(help || "")}</small>
            </div>
          `
        )
        .join("")}
    </div>
    <div class="radar-facts">
      <strong>Facts</strong>
      <ul>${(item.facts || []).map((fact) => `<li>${escapeHtml(fact)}</li>`).join("")}</ul>
    </div>
  `;
  return article;
}

async function generateOpeningAdvice() {
  els.generateOpeningAdviceButton.disabled = true;
  els.generateOpeningAdviceButton.textContent = "Thinking";
  els.openingAdviceMeta.textContent = "MiniMax running";
  try {
    if (!openingRadarSnapshot) await loadOpeningRadar({force: true});
    const data = await api("/api/opening-radar/advice", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({report_id: openingRadarReportId}),
    });
    openingRadarSnapshot = data;
    openingRadarReportId = data.report?.id || openingRadarReportId;
    renderOpeningRadar(data);
  } catch (error) {
    els.openingAdviceBody.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    els.openingAdviceMeta.textContent = "Failed";
  } finally {
    els.generateOpeningAdviceButton.disabled = false;
  els.generateOpeningAdviceButton.textContent = "AI Prep";
  }
}

function renderOpeningAdvice(provider, advice) {
  els.openingAdviceMeta.textContent = `${escapeHtml(provider || advice.provider || "MiniMax")} · C ${Number(advice.confidence_score || 0).toFixed(0)}`;
  els.openingAdviceBody.innerHTML = `
    <section class="advice-block wide">
      <h3>Market Call</h3>
      <p>${escapeHtml(advice.market_call || advice.summary || "No market call returned.")}</p>
    </section>
    ${adviceList("Today Plan", advice.today_plan)}
    ${adviceList("Risk Controls", advice.risk_controls)}
    ${adviceList("Watch Levels", advice.watch_levels)}
  `;
}

function adviceList(title, items) {
  const safeItems = Array.isArray(items) ? items.filter(Boolean) : [];
  return `
    <section class="advice-block">
      <h3>${escapeHtml(title)}</h3>
      ${safeItems.length ? `<ul>${safeItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : `<p>No items.</p>`}
    </section>
  `;
}

function numberText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return Math.abs(number) >= 100 ? number.toFixed(0) : number.toFixed(2);
}

function rsiLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (number >= 70) return "overbought";
  if (number <= 30) return "oversold";
  if (number >= 55) return "bullish zone";
  if (number <= 45) return "weak zone";
  return "neutral";
}

function kdjLabel(indicators) {
  const k = Number(indicators.kdj_k);
  const d = Number(indicators.kdj_d);
  if (!Number.isFinite(k) || !Number.isFinite(d)) return "-";
  if (k > 80) return "hot";
  if (k < 20) return "cold";
  return k > d ? "turning up" : "turning down";
}

function adxLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (number >= 25) return "trend strong";
  if (number < 18) return "range likely";
  return "trend forming";
}

function volatilityText(item) {
  const vol = item.volatility || {};
  if (vol.latest) return `${numberText(vol.latest)} / ${numberText(item.indicators?.realized_vol_20d)}%`;
  return `${numberText(item.indicators?.realized_vol_20d)}%`;
}

async function loadDataSources({force = false} = {}) {
  if (datasourcesLoaded && !force) return;
  els.datasourceList.innerHTML = `<div class="empty">Loading datasources</div>`;
  try {
    const data = await api("/api/datasources");
    renderDataSources(data.sources || [], data.summary || {});
    datasourcesLoaded = true;
  } catch (error) {
    els.datasourceList.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderDataSources(sources, summary) {
  const scopeOrder = ["base", "sector", "ticker", "optional"];
  const activeCount = sources.filter((source) => source.status === "active").length;
  const plannedCount = sources.length - activeCount;
  els.datasourceSummary.innerHTML = `
    <span>${activeCount} active</span>
    <span>${plannedCount} planned</span>
    ${scopeOrder.map((scope) => `<span>${escapeHtml(scopeLabel(scope))} ${Number(summary[scope] || 0)}</span>`).join("")}
  `;
  if (!sources.length) {
    els.datasourceList.innerHTML = `<div class="empty">No datasources registered</div>`;
    return;
  }
  const grouped = groupDataSources(sources);
  els.datasourceList.innerHTML = "";
  for (const group of grouped) {
    const section = document.createElement("section");
    section.className = "datasource-group";
    section.innerHTML = `
      <div class="datasource-group-head">
        <h3>${escapeHtml(scopeLabel(group.scope))}</h3>
        <span>${group.items.length}</span>
      </div>
    `;
    for (const source of group.items) {
      section.appendChild(renderDataSourceCard(source));
    }
    els.datasourceList.appendChild(section);
  }
}

function groupDataSources(sources) {
  const order = ["base", "sector", "ticker", "optional"];
  const byScope = new Map();
  for (const source of sources) {
    const scope = source.collection_scope || "optional";
    if (!byScope.has(scope)) byScope.set(scope, []);
    byScope.get(scope).push(source);
  }
  return [...byScope.entries()]
    .sort(([left], [right]) => scopeRank(left, order) - scopeRank(right, order))
    .map(([scope, items]) => ({
      scope,
      items: items.sort((a, b) => String(a.source_key).localeCompare(String(b.source_key))),
    }));
}

function renderDataSourceCard(source) {
  const article = document.createElement("article");
  article.className = "datasource-card";
  article.dataset.status = source.status || "active";
  const dimensions = Array.isArray(source.dimensions) ? source.dimensions : [];
  const keywords = Array.isArray(source.applies_to_keywords) ? source.applies_to_keywords : [];
  const tickers = Array.isArray(source.applies_to_tickers) ? source.applies_to_tickers : [];
  const notes = Array.isArray(source.notes) ? source.notes : [];
  article.innerHTML = `
    <div class="datasource-card-head">
      <div>
        <strong>${escapeHtml(source.source_name || source.source_key)}</strong>
        <span>${escapeHtml(source.source_key || "")} · ${escapeHtml(source.source_type || "")}</span>
      </div>
      <mark>${escapeHtml(statusLabel(source.status, source.enabled))}</mark>
    </div>
    <div class="datasource-purpose">
      <b>Purpose</b>
      <span>${escapeHtml(source.purpose_en || "-")}</span>
      ${textSupplement(source.purpose_zh)}
    </div>
    <div class="datasource-meta-grid">
      <span><b>Provider</b>${escapeHtml(source.provider || "-")}</span>
      <span><b>Scope</b>${escapeHtml(scopeLabel(source.collection_scope))}</span>
      <span><b>Trust</b>${Number(source.trust_level || 0)}</span>
      <span><b>Auth</b>${escapeHtml(source.auth || "none")}</span>
    </div>
    <div class="datasource-links">
      ${source.website_url ? `<a href="${escapeHtml(source.website_url)}" target="_blank" rel="noreferrer">Website</a>` : ""}
      ${source.docs_url ? `<a href="${escapeHtml(source.docs_url)}" target="_blank" rel="noreferrer">Docs</a>` : ""}
    </div>
    ${dimensions.length ? `<div class="datasource-chip-row">${dimensions.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    ${scopeDetail(keywords, tickers)}
    <div class="datasource-detail-line"><b>Limits</b><span>${escapeHtml(source.rate_limit_summary || "-")}</span>${textSupplement(source.rate_limit_summary_zh)}</div>
    <div class="datasource-detail-line"><b>Cache</b><span>${escapeHtml(source.cache_policy || "-")}</span>${textSupplement(source.cache_policy_zh)}</div>
    ${notes.length ? `<p class="datasource-note">${escapeHtml(notes.join(" "))}</p>` : ""}
  `;
  return article;
}

function textSupplement(supplement) {
  if (!supplement) return "";
  return `<small>${escapeHtml(supplement)}</small>`;
}

function scopeDetail(keywords, tickers) {
  if (!keywords.length && !tickers.length) return "";
  return `
    <div class="datasource-scope-detail">
      ${keywords.length ? `<span><b>Keywords</b>${escapeHtml(keywords.slice(0, 8).join(" · "))}${keywords.length > 8 ? " ..." : ""}</span>` : ""}
      ${tickers.length ? `<span><b>Tickers</b>${escapeHtml(tickers.slice(0, 12).join(" · "))}${tickers.length > 12 ? " ..." : ""}</span>` : ""}
    </div>
  `;
}

function scopeRank(scope, order) {
  const index = order.indexOf(scope);
  return index < 0 ? 99 : index;
}

function scopeLabel(scope) {
  const labels = {
    base: "Base",
    optional: "Optional",
    sector: "Sector Scoped",
    ticker: "Ticker Scoped",
  };
  return labels[scope] || String(scope || "Optional");
}

function statusLabel(status, enabled) {
  if (status === "planned") return "Planned";
  return enabled === false ? "Disabled" : "Active";
}

function setCandidateSearchMode(isSearching) {
  els.minScore.disabled = isSearching;
  els.perSector.disabled = isSearching;
  els.minScore.closest("label")?.classList.toggle("is-disabled", isSearching);
  els.perSector.closest("label")?.classList.toggle("is-disabled", isSearching);
  els.candidateList.dataset.mode = isSearching ? "search" : "ranked";
}

async function refreshRuns() {
  const data = await api("/api/runs");
  const monitor = data.monitor || {};
  const latestRun = monitor.latest_run || null;
  const isRunning = Boolean(data.worker.running || Number(monitor.active_count || 0));
  const latestRunId = monitor.latest_run_id || data.worker.last_run_id;
  els.workerState.textContent = isRunning ? "RUNNING" : "IDLE";
  els.workerState.dataset.status = isRunning ? "running" : "idle";
  els.latestRun.textContent = latestRunId ? `RUN ${latestRunId}` : "RUN -";
  els.latestRun.dataset.status = latestRun ? latestRun.status.toLowerCase() : isRunning ? "running" : "idle";
  renderRunMonitor(monitor);
  renderQueue(data.worker.queue || {}, monitor);
}

function renderQueue(queue, monitor = {}) {
  const status = queue.status || "idle";
  const current = queue.current ? [queue.current] : [];
  const pending = queue.pending || [];
  const completed = queue.completed || [];
  const failed = queue.failed || [];
  const activeRun = (monitor.active_runs || [])[0] || null;
  const latestRun = monitor.latest_run || null;
  els.queueStage.textContent = activeRun
    ? `DB Run ${activeRun.id} · ${runStatusText(activeRun.status)}`
    : queue.stage || status.toUpperCase();
  els.queueStage.dataset.status = activeRun ? activeRun.status.toLowerCase() : status;
  const total = Number(queue.total || 0);
  const doneCount = completed.length + failed.length;
  if (activeRun) {
    els.queueProgress.textContent = `${Number(activeRun.progress?.percent || 0).toFixed(1)}% · ${activeRun.total} tickers · ${formatShortTime(activeRun.latest_activity_at)}`;
  } else if (latestRun) {
    els.queueProgress.textContent = `No active run · latest DB run ${latestRun.id} ${runStatusText(latestRun.status)}`;
  } else {
    els.queueProgress.textContent = total ? `${doneCount}/${total} completed` : "No active run";
  }
  renderTickerPills(els.queueCurrent, current, "None");
  renderTickerPills(els.queuePending, pending, "None");
  renderTickerPills(els.queueCompleted, completed, "None");
  renderTickerPills(els.queueFailed, failed, "None");
  els.queueCurrentCount.textContent = String(current.length);
  els.queuePendingCount.textContent = String(pending.length);
  els.queueCompletedCount.textContent = String(completed.length);
  els.queueFailedCount.textContent = String(failed.length);
}

function renderRunMonitor(monitor) {
  const activeRuns = monitor.active_runs || [];
  const recentRuns = monitor.recent_runs || [];
  const latestRun = monitor.latest_run || null;
  if (activeRuns.length) {
    els.monitorSummary.textContent = `${activeRuns.length} active · latest run ${monitor.latest_run_id}`;
  } else if (latestRun) {
    els.monitorSummary.textContent = `Idle · latest run ${latestRun.id} ${runStatusText(latestRun.status)}`;
  } else {
    els.monitorSummary.textContent = "No database runs";
  }

  els.activeRunList.innerHTML = "";
  if (!activeRuns.length) {
    els.activeRunList.innerHTML = `<div class="monitor-empty">No active database run. Recent runs are below.</div>`;
  } else {
    for (const run of activeRuns) {
      els.activeRunList.appendChild(renderRunCard(run, {compact: false}));
    }
  }

  els.recentRunCount.textContent = String(recentRuns.length);
  els.recentRunList.innerHTML = "";
  if (!recentRuns.length) {
    els.recentRunList.textContent = "None";
    els.recentRunList.classList.add("muted");
    return;
  }
  els.recentRunList.classList.remove("muted");
  for (const run of recentRuns.slice(0, 10)) {
    els.recentRunList.appendChild(renderRunCard(run, {compact: true}));
  }
}

function renderRunCard(run, {compact}) {
  const article = document.createElement("article");
  article.className = compact ? "run-card compact" : "run-card";
  article.dataset.status = run.status.toLowerCase();
  const percent = Number(run.progress?.percent || 0);
  const errorCount = Number(run.progress?.error_observations || 0);
  const dims = run.dimensions || [];
  const sources = run.sources || [];
  const tickers = run.tickers || [];
  const config = run.config || {};
  article.innerHTML = `
    <div class="run-card-head">
      <div>
        <strong>Run ${Number(run.id || 0)}</strong>
        <span>${escapeHtml(run.trigger || "manual")} · ${Number(run.total || 0)} tickers${config.screen_mode ? ` · ${escapeHtml(config.screen_mode)}` : ""}</span>
      </div>
      <mark>${runStatusText(run.status)}</mark>
    </div>
    <div class="run-progress-line">
      <span>${percent.toFixed(1)}%${errorCount ? ` · ${errorCount} data errors` : ""}</span>
      <span>${escapeHtml(formatShortTime(run.latest_activity_at || run.finished_at || run.started_at))}</span>
    </div>
    <div class="progress-bar"><span style="width:${Math.min(percent, 100)}%"></span></div>
    ${compact ? "" : runStats(run)}
    ${sourceChips(compact ? sources.slice(0, 5) : sources)}
    ${dimensionChips(compact ? dims.slice(0, 6) : dims)}
    ${compact ? "" : tickerPreview(tickers, run.total)}
    ${run.error_message ? `<p class="run-error">${escapeHtml(run.error_message).slice(0, 220)}</p>` : ""}
  `;
  return article;
}

function runStats(run) {
  const progress = run.progress || {};
  return `
    <div class="run-stats">
      <span><strong>${Number(progress.completed_slots || 0)}</strong><em>done slots</em></span>
      <span><strong>${Number(progress.expected_slots || 0)}</strong><em>expected</em></span>
      <span><strong>${Number(progress.scored_tickers || 0)}</strong><em>scored</em></span>
      <span><strong>${Number(progress.error_observations || 0)}</strong><em>errors</em></span>
    </div>
  `;
}

function sourceChips(sources) {
  if (!sources.length) return "";
  return `
    <div class="source-chips" aria-label="Requested datasources">
      ${sources
        .map((item) => {
          const total = Number(item.total || 0);
          const count = Number(item.ticker_count || 0);
          const scoped = ["sector", "ticker"].includes(String(item.collection_scope || ""));
          const state = count ? "done" : scoped ? "scoped" : "empty";
          const label = sourceShortLabel(item.source_name || item.source_key);
          const countText = scoped ? String(count) : `${count}/${total}`;
          const title = `${item.source_key} · ${scopeLabel(item.collection_scope)} · ${Number(item.observation_count || 0)} observations`;
          return `<span data-state="${state}" title="${escapeHtml(title)}">${escapeHtml(label)} <b>${escapeHtml(countText)}</b></span>`;
        })
        .join("")}
    </div>
  `;
}

function dimensionChips(dimensions) {
  if (!dimensions.length) return "";
  return `
    <div class="dimension-chips">
      ${dimensions
        .map((item) => {
          const total = Number(item.total || 0);
          const count = Number(item.ticker_count || 0);
          const state = total && count >= total ? "done" : count ? "partial" : "empty";
          return `<span data-state="${state}" title="${escapeHtml(item.key)}">${escapeHtml(item.label)} <b>${count}/${total}</b></span>`;
        })
        .join("")}
    </div>
  `;
}

function sourceShortLabel(value) {
  return String(value || "")
    .replace("Yahoo Finance via ", "")
    .replace("SEC DEF 14A / 10-K Ownership Tables", "SEC Ownership")
    .replace("SEC Schedule 13D/G", "SEC 13D/G")
    .replace("Company Official Sources", "Official")
    .replace("USAspending.gov", "USAspending");
}

function tickerPreview(tickers, total) {
  if (!tickers.length) return "";
  const more = Number(total || 0) - tickers.length;
  return `<p class="ticker-preview">${tickers.map(escapeHtml).join(" · ")}${more > 0 ? ` · +${more}` : ""}</p>`;
}

function runStatusText(status) {
  const clean = String(status || "unknown").toUpperCase();
  if (clean === "RUNNING") return "Running";
  if (clean === "DONE") return "Done";
  if (clean === "FAILED") return "Failed";
  return clean;
}

function formatShortTime(value) {
  if (!value) return "no activity";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return date.toLocaleString("en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderTickerPills(container, tickers, emptyText) {
  container.innerHTML = "";
  if (!tickers.length) {
    container.textContent = emptyText;
    container.classList.add("muted");
    return;
  }
  container.classList.remove("muted");
  for (const ticker of tickers) {
    const span = document.createElement("span");
    span.textContent = ticker;
    container.appendChild(span);
  }
}

function flattenGroups(groups) {
  return groups.flatMap((group) => group.candidates || []);
}

function normalizeCandidateGroups(groups, searchTerm) {
  if (!searchTerm) return groups;
  const candidates = flattenGroups(groups).sort((a, b) => {
    const rankDiff = candidateSearchRank(a, searchTerm) - candidateSearchRank(b, searchTerm);
    if (rankDiff) return rankDiff;
    return Number(b.total_score || 0) - Number(a.total_score || 0);
  });
  return candidates.length ? [{sector: "Search Results", candidates}] : [];
}

function filterGroupsByPool(groups, poolKey) {
  if (poolKey === "all") return groups;
  const filtered = [];
  for (const group of groups) {
    const candidates = (group.candidates || []).filter((item) => candidatePoolKeys(item).includes(poolKey));
    if (candidates.length) filtered.push({...group, candidates, count: candidates.length});
  }
  return filtered;
}

function candidatePoolCounts(candidates) {
  const counts = {all: candidates.length, futu: 0, watched: 0};
  for (const item of candidates) {
    for (const key of candidatePoolKeys(item)) {
      if (key in counts) counts[key] += 1;
    }
  }
  return counts;
}

function renderCandidatePools(counts) {
  const pools = [
    {key: "all", label: "All"},
    {key: "futu", label: "Futu Screen"},
    {key: "watched", label: "Watchlist"},
  ];
  els.candidatePoolList.innerHTML = "";
  for (const pool of pools) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `candidate-pool-button${activePool === pool.key ? " active" : ""}`;
    button.innerHTML = `<span>${escapeHtml(pool.label)}</span><b>${Number(counts[pool.key] || 0)}</b>`;
    button.addEventListener("click", async () => {
      activePool = pool.key;
      await refreshAll();
    });
    els.candidatePoolList.appendChild(button);
  }
}

function candidatePoolKeys(item) {
  const keys = ["scored"];
  if (item.futu_code || item.sector || item.industry || item.sector_group) keys.push("futu");
  if (latestWatchlist.has(tickerKey(item))) keys.push("watched");
  return keys;
}

function candidateSearchRank(item, searchTerm) {
  const needle = searchTerm.toLowerCase();
  const ticker = String(item.ticker || "").toLowerCase();
  const futuCode = String(item.futu_code || "").toLowerCase();
  const name = String(item.name || "").toLowerCase();
  if (ticker === needle || futuCode === needle) return 0;
  if (ticker.startsWith(needle) || futuCode.startsWith(needle)) return 1;
  if (name.startsWith(needle)) return 2;
  if (ticker.includes(needle) || futuCode.includes(needle)) return 3;
  if (name.includes(needle)) return 4;
  return 5;
}

function renderCandidateGroups(groups, options = {}) {
  const emptyText = options.emptyText || "No candidates";
  const searchTerm = options.searchTerm || "";
  const total = groups.reduce((count, group) => count + (group.candidates || []).length, 0);
  els.candidateCount.textContent = String(total);
  els.candidateList.innerHTML = "";
  if (!total) {
    els.candidateList.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  for (const group of groups) {
    const section = document.createElement("section");
    section.className = "sector-group";
    const candidates = group.candidates || [];
    section.innerHTML = `
      <div class="sector-head">
        <h3>${escapeHtml(group.sector || "Unclassified")}</h3>
        <span>${candidates.length}</span>
      </div>
    `;
    for (const item of candidates) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `candidate-row${item.ticker === selectedTicker ? " active" : ""}`;
      button.innerHTML = `
        <span>
          <span class="ticker">${highlightMatch(item.ticker, searchTerm)} · ${escapeHtml(item.grade || "-")}</span>
          <span class="name">${highlightMatch(item.name || "Unknown", searchTerm)}</span>
          <span class="candidate-meta">#${Number(item.sector_rank || 0)} · ${escapeHtml(item.industry || item.sector_group || item.sector || "Unclassified")}</span>
          ${candidateMembershipMarkup(item)}
        </span>
        <span class="score">${Number(item.total_score || 0).toFixed(1)}</span>
      `;
      button.addEventListener("click", async () => {
        selectedTicker = item.ticker;
        await refreshAll();
      });
      section.appendChild(button);
    }
    els.candidateList.appendChild(section);
  }
}

function candidateMembershipMarkup(item) {
  const chips = [];
  const keys = candidatePoolKeys(item);
  if (keys.includes("futu")) chips.push({source: "futu", label: "Futu"});
  if (keys.includes("watched")) chips.push({source: "watched", label: "Watch"});
  chips.push({source: "scored", label: "Scored"});
  return `
    <span class="candidate-memberships">
      ${chips.map((chip) => `<span data-source="${escapeHtml(chip.source)}">${escapeHtml(chip.label)}</span>`).join("")}
    </span>
  `;
}

function highlightMatch(value, searchTerm) {
  const text = String(value ?? "");
  const needle = String(searchTerm || "").trim();
  if (!needle) return escapeHtml(text);
  const index = text.toLowerCase().indexOf(needle.toLowerCase());
  if (index < 0) return escapeHtml(text);
  const end = index + needle.length;
  return `${escapeHtml(text.slice(0, index))}<mark class="candidate-match">${escapeHtml(text.slice(index, end))}</mark>${escapeHtml(text.slice(end))}`;
}

async function loadTicker(ticker) {
  const requestedTicker = ticker.toUpperCase();
  const dimension = els.dimensionFilter.value;
  const data = await api(`/api/ticker/${requestedTicker}?dimension=${encodeURIComponent(dimension)}&min_importance=0`);
  if (requestedTicker !== selectedTicker) return;
  els.detailTitle.textContent = requestedTicker;
  els.detailScore.textContent = data.score ? `${Number(data.score.total_score).toFixed(1)} · ${data.score.grade}` : "-";
  if (activeDetailTab === "chart") renderTradingViewChart(requestedTicker);
  renderLastRun(data.last_run);
  renderScore(data.score);
  renderMissing(data.score);
  renderTimeline(data.timeline || []);
  await Promise.all([loadCompanySummary(requestedTicker), loadTickerFuture(requestedTicker), loadTickerTrend(requestedTicker)]);
}

function clearTickerDetail() {
  els.detailTitle.textContent = "Ticker";
  els.detailScore.textContent = "-";
  els.detailLastRun.textContent = "Last trigger -";
  els.rerunTickerButton.disabled = true;
  els.refreshTimetableButton.disabled = true;
  setWatchState(false);
  els.summaryMeta.textContent = "LLM prompt summary";
  els.summaryBody.innerHTML = `<div class="empty">No summary yet</div>`;
  els.summaryButton.disabled = false;
  els.summaryButton.textContent = "Regenerate";
  els.missingData.innerHTML = "";
  els.scoreBreakdown.innerHTML = "";
  els.timeline.innerHTML = `<div class="empty">No truth items</div>`;
  els.timetableStatus.textContent = "Official and configured event sources";
  els.futureTimeline.innerHTML = `<div class="empty">No timetable items</div>`;
  renderTrend(null);
  renderTradingViewChart(null);
}

function renderLastRun(run) {
  els.rerunTickerButton.disabled = !selectedTicker;
  els.refreshTimetableButton.disabled = !selectedTicker;
  if (!run) {
    els.detailLastRun.textContent = "Last trigger -";
    return;
  }
  const trigger = run.trigger || "manual";
  const status = runStatusText(run.status);
  const started = formatShortTime(run.started_at);
  els.detailLastRun.textContent = `Last trigger ${trigger} · ${status} · ${started}`;
}

function setDetailTab(tab) {
  activeDetailTab = tab;
  const entries = [
    ["summary", els.summaryTab, els.summaryPanel],
    ["truth", els.truthTab, els.truthPanel],
    ["timetable", els.timetableTab, els.timetablePanel],
    ["chart", els.chartTab, els.chartPanel],
  ];
  for (const [key, tabButton, panel] of entries) {
    tabButton.classList.toggle("active", key === tab);
    panel.classList.toggle("active", key === tab);
  }
  const truthActive = tab === "truth";
  els.dimensionFilter.disabled = !truthActive;
  els.dimensionFilter.closest("label")?.classList.toggle("is-disabled", !truthActive);
  if (tab === "timetable" && selectedTicker) loadTickerFuture(selectedTicker);
  if (tab === "chart") renderTradingViewChart(selectedTicker);
}

function renderTradingViewChart(ticker) {
  if (!ticker) {
    tradingViewLoadedTicker = null;
    els.tradingViewWidget.classList.remove("is-ready", "is-error");
    els.tradingViewLink.href = "https://www.tradingview.com/";
    els.tradingViewLink.textContent = "Open TradingView";
    els.tradingViewWidget.innerHTML = `<div class="empty">Select a ticker</div>`;
    return;
  }
  const cleanTicker = ticker.toUpperCase();
  const symbol = tradingViewSymbol(cleanTicker);
  const chartUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`;
  els.tradingViewLink.href = chartUrl;
  els.tradingViewLink.textContent = `Open ${cleanTicker}`;
  if (tradingViewLoadedTicker === cleanTicker && !els.tradingViewWidget.classList.contains("is-error")) return;
  tradingViewLoadedTicker = cleanTicker;
  els.tradingViewWidget.classList.remove("is-ready", "is-error");
  els.tradingViewWidget.innerHTML = `
    <div class="tradingview-loading">
      <strong>Loading chart</strong>
      <span>Checking TradingView widget access</span>
    </div>
    <div class="tradingview-error">
      <strong>Embedded chart unavailable</strong>
      <span>The TradingView widget domain cannot be reached from this browser/network. The full TradingView page can still open normally.</span>
      <a href="${escapeHtml(chartUrl)}" target="_blank" rel="noreferrer">Open ${escapeHtml(cleanTicker)}</a>
    </div>
    <div class="tradingview-widget-container__widget"></div>
  `;
  ensureTradingViewWidgetAccess(cleanTicker).then((reachable) => {
    if (tradingViewLoadedTicker !== cleanTicker) return;
    if (!reachable) {
      showTradingViewError(cleanTicker);
      return;
    }
    injectTradingViewWidget(symbol, cleanTicker);
  });
}

function injectTradingViewWidget(symbol, ticker) {
  const widget = els.tradingViewWidget.querySelector(".tradingview-widget-container__widget");
  if (!widget) return;
  const script = document.createElement("script");
  script.type = "text/javascript";
  script.async = true;
  script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
  script.onerror = () => {
    if (tradingViewLoadedTicker === ticker) showTradingViewError(ticker);
  };
  script.textContent = JSON.stringify({
    autosize: true,
    symbol,
    interval: "D",
    timezone: "America/New_York",
    theme: "dark",
    style: "1",
    locale: "en",
    allow_symbol_change: true,
    save_image: false,
    calendar: false,
    hide_volume: false,
    support_host: "https://www.tradingview.com",
  });
  widget.appendChild(script);
  watchTradingViewFrame(ticker);
}

function tradingViewSymbol(ticker) {
  return String(ticker || "").trim().toUpperCase().replace(/[^A-Z0-9._-]/g, "");
}

async function ensureTradingViewWidgetAccess(ticker) {
  if (navigator.webdriver === true) return false;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 4500);
  try {
    await fetch("https://www.tradingview-widget.com/embed-widget/advanced-chart/", {
      mode: "no-cors",
      cache: "no-store",
      signal: controller.signal,
    });
    return true;
  } catch (error) {
    console.info(`TradingView embedded widget unavailable for ${ticker}: ${error.message}`);
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

function watchTradingViewFrame(ticker) {
  const container = els.tradingViewWidget;
  let fallbackTimer = null;
  const markReady = () => {
    if (tradingViewLoadedTicker !== ticker || container.classList.contains("is-error")) return;
    window.clearTimeout(fallbackTimer);
    container.classList.add("is-ready");
  };
  const attach = () => {
    const iframe = container.querySelector("iframe");
    if (!iframe) return false;
    iframe.addEventListener("load", markReady, {once: true});
    fallbackTimer = window.setTimeout(() => {
      if (tradingViewLoadedTicker === ticker && !container.classList.contains("is-ready")) {
        showTradingViewError(ticker);
      }
    }, 9000);
    return true;
  };
  if (attach()) return;
  const observer = new MutationObserver(() => {
    if (attach()) observer.disconnect();
  });
  observer.observe(container, {childList: true, subtree: true});
  window.setTimeout(() => observer.disconnect(), 8000);
}

function showTradingViewError(ticker) {
  if (tradingViewLoadedTicker !== ticker) return;
  els.tradingViewWidget.classList.remove("is-ready");
  els.tradingViewWidget.classList.add("is-error");
}

function renderScore(score) {
  els.scoreBreakdown.innerHTML = "";
  if (!score) {
    els.scoreBreakdown.innerHTML = `<div class="empty">No score</div>`;
    return;
  }
  const components = score.component_scores || {};
  const rows = [
    {label: "Eligibility", help: "Market-cap fit and hidden-champion profile", value: components.eligibility ?? components.size},
    {label: "Valuation", help: "P/E and valuation discipline", value: components.valuation},
    {label: "Growth", help: "Revenue growth and quality of growth", value: components.growth_quality ?? components.growth},
    {label: "Orders", help: "Backlog/RPO visibility and order evidence", value: components.order_quality ?? components.backlog_rpo},
    {label: "Ownership", help: "Insider and institutional alignment", value: components.ownership_alignment ?? components.ownership},
    {label: "Quality", help: "Margins, cash flow, and leverage", value: components.financial_quality},
    {label: "Attention", help: "Main-money flow, momentum, and crowding", value: components.attention_flow},
    {label: "Info", help: "Source coverage and evidence strength", value: components.information_quality},
  ];
  for (const row of rows) {
    const div = document.createElement("div");
    div.className = "metric";
    div.innerHTML = `
      <strong>
        <span>${escapeHtml(row.label)}</span>
      </strong>
      <span class="metric-value">${Number(row.value || 0).toFixed(1)}</span>
      <small>${escapeHtml(row.help)}</small>
    `;
    els.scoreBreakdown.appendChild(div);
  }
}

function renderMissing(score) {
  els.missingData.innerHTML = "";
  if (!score || !score.missing_dimensions || !score.missing_dimensions.length) return;
  const items = score.missing_dimensions.map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  els.missingData.innerHTML = `<strong>Missing</strong>${items}`;
}

async function loadCompanySummary(ticker) {
  els.summaryMeta.textContent = "LLM prompt summary";
  els.summaryButton.disabled = false;
  els.summaryButton.textContent = "Regenerate";
  els.summaryBody.innerHTML = `<div class="empty">Loading summary</div>`;
  try {
    const data = await api(`/api/ticker/${ticker}/summary`);
    if (ticker !== selectedTicker) return;
    renderCompanySummary(data.summary);
  } catch (error) {
    els.summaryBody.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderCompanySummary(summary) {
  if (!summary) {
    els.summaryMeta.textContent = "Not generated";
    els.summaryButton.textContent = "Regenerate";
    els.summaryBody.innerHTML = `<div class="empty">Generate an LLM summary from collected evidence.</div>`;
    return;
  }
  els.summaryMeta.textContent = `${escapeHtml(summary.provider || "minimax")} · ${escapeHtml((summary.created_at || "").slice(0, 10))} · C ${Number(summary.confidence_score || 0).toFixed(0)}`;
  els.summaryButton.textContent = "Regenerate";
  els.summaryBody.innerHTML = `
    <div class="summary-section summary-wide">
      <h4>Business</h4>
      <p>${escapeHtml(summary.business || "Insufficient evidence.")}</p>
    </div>
    <div class="summary-section summary-wide">
      <h4>Industry Role</h4>
      <p>${escapeHtml(summary.industry_role || "Insufficient evidence.")}</p>
    </div>
    ${summaryList("Thesis", summary.recommendation_reason)}
    ${summaryList("Risks", summary.risks)}
    ${summaryList("Watch Items", summary.watch_items)}
  `;
}

function summaryList(title, items) {
  const safeItems = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!safeItems.length) {
    return `
      <div class="summary-section">
        <h4>${escapeHtml(title)}</h4>
        <p>Insufficient evidence.</p>
      </div>
    `;
  }
  return `
    <div class="summary-section">
      <h4>${escapeHtml(title)}</h4>
      <ul>${safeItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
  `;
}

function renderTimeline(items) {
  els.timeline.innerHTML = "";
  if (!items.length) {
    els.timeline.innerHTML = `<div class="empty">No truth items</div>`;
    return;
  }
  for (const item of items) {
    const div = document.createElement("article");
    div.className = "timeline-item";
    div.innerHTML = `
      <div class="timeline-meta">
        <span class="badge">${escapeHtml(item.dimension)}</span>
        <span class="badge">${escapeHtml(item.source_key)}</span>
        <span class="badge">I ${Number(item.importance_score || 0).toFixed(0)}</span>
        <span class="badge">${escapeHtml((item.event_date || item.created_at || "").slice(0, 10))}</span>
      </div>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.summary || "")}</p>
      ${item.raw_excerpt ? `<div class="excerpt">${escapeHtml(item.raw_excerpt.slice(0, 900))}</div>` : ""}
      <details>
        <summary>Evidence</summary>
        <pre>${escapeHtml(JSON.stringify(item.evidence || {}, null, 2).slice(0, 5000))}</pre>
      </details>
    `;
    els.timeline.appendChild(div);
  }
}

async function loadTickerFuture(ticker) {
  try {
    els.timetableStatus.textContent = "Loading timetable";
    const data = await api(`/api/ticker/${ticker}/future`);
    if (ticker !== selectedTicker) return;
    setWatchState(Boolean(data.watched));
    renderFutureEvents(data.events || []);
  } catch (error) {
    els.timetableStatus.textContent = "Timetable unavailable";
    els.futureTimeline.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderFutureEvents(events) {
  els.futureTimeline.innerHTML = "";
  els.timetableStatus.textContent = `${events.length} upcoming event${events.length === 1 ? "" : "s"}`;
  if (!events.length) {
    els.futureTimeline.innerHTML = `<div class="empty">No timetable items</div>`;
    return;
  }
  let lastDate = "";
  for (const event of events) {
    const article = document.createElement("article");
    article.className = "future-event";
    const dateLabel = event.event_date || event.window_label || "TBD";
    const isNewDate = dateLabel !== lastDate;
    lastDate = dateLabel;
    article.innerHTML = `
      <div class="event-date ${isNewDate ? "" : "muted-date"}">
        <strong>${escapeHtml(dateLabel)}</strong>
        ${event.window_label && event.window_label !== event.event_date ? `<span>${escapeHtml(event.window_label)}</span>` : ""}
      </div>
      <div class="event-body">
        <div class="event-meta">
          <span>${escapeHtml(event.catalyst_type || "event")}</span>
          <span>${escapeHtml(event.status || "WATCH")}</span>
          <span>I ${Number(event.importance_score || 0).toFixed(0)}</span>
          ${event.configured ? `<span>configured</span>` : ""}
        </div>
        <h3>${escapeHtml(event.title || "Untitled event")}</h3>
        <p>${escapeHtml(event.summary || "")}</p>
        ${event.source_url ? `<a class="event-source" href="${escapeAttribute(event.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(event.source_key || "source")}</a>` : ""}
      </div>
    `;
    els.futureTimeline.appendChild(article);
  }
}

async function refreshTimetableSources() {
  if (!selectedTicker) return;
  const ticker = selectedTicker;
  els.refreshTimetableButton.disabled = true;
  els.refreshTimetableButton.textContent = "Refreshing";
  els.timetableStatus.textContent = "Starting official event-source run";
  try {
    await api("/api/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        tickers: ticker,
        screen_mode: "tickers",
        screen_condition: "",
        screen_limit: 1,
        use_futu: false,
        use_sec: false,
        use_yfinance: false,
        use_13f: false,
        use_usaspending: false,
        use_launch_library: true,
        use_company_official: true,
        use_openinsider: false,
        summarize: false,
        delay_seconds: 0.2,
      }),
    });
    els.timetableStatus.textContent = "Event-source run started";
    openQueueDrawer();
    window.setTimeout(() => {
      if (ticker === selectedTicker) loadTickerFuture(ticker);
    }, 2200);
  } catch (error) {
    els.timetableStatus.textContent = error.message;
  } finally {
    els.refreshTimetableButton.disabled = !selectedTicker;
    els.refreshTimetableButton.textContent = "Refresh Events";
  }
}

async function loadTickerTrend(ticker) {
  els.trendReturn.textContent = "-";
  els.trendRange.textContent = "Loading";
  els.trendPrice.textContent = "-";
  els.trendChartBody.innerHTML = `<div class="trend-empty">Loading trend</div>`;
  try {
    const data = await api(`/api/ticker/${ticker}/trend?max_points=420`);
    if (ticker !== selectedTicker) return;
    renderTrend(data);
  } catch (error) {
    if (ticker !== selectedTicker) return;
    renderTrend({points: [], error: error.message});
  }
}

function renderTrend(trend) {
  if (!trend) {
    els.trendReturn.textContent = "-";
    els.trendReturn.title = "Total return from first weekly close to latest weekly close.";
    els.trendRange.textContent = "Futu weekly close";
    els.trendPrice.textContent = "-";
    els.trendChartBody.innerHTML = `<div class="trend-empty">No trend loaded</div>`;
    return;
  }
  const points = Array.isArray(trend.points) ? trend.points.filter((point) => Number.isFinite(Number(point.close))) : [];
  if (trend.error || points.length < 2) {
    const errorText = trend.error ? shortTrendError(trend.error) : "Not enough history";
    els.trendReturn.textContent = "-";
    els.trendReturn.title = "Total return from first weekly close to latest weekly close.";
    els.trendRange.textContent = trend.source_label || "Futu weekly close";
    els.trendPrice.textContent = "-";
    els.trendChartBody.innerHTML = `<div class="trend-empty">${escapeHtml(errorText)}</div>`;
    return;
  }
  const closes = points.map((point) => Number(point.close));
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const width = 560;
  const height = 140;
  const pad = 10;
  const usableWidth = width - pad * 2;
  const usableHeight = height - pad * 2;
  const path = points
    .map((point, index) => {
      const x = pad + (index / (points.length - 1)) * usableWidth;
      const y = pad + (1 - (Number(point.close) - min) / span) * usableHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const totalReturn = Number(trend.total_return);
  const returnText = Number.isFinite(totalReturn) ? `${totalReturn >= 0 ? "+" : ""}${(totalReturn * 100).toFixed(0)}%` : "-";
  const latestClose = Number(trend.latest_close ?? closes[closes.length - 1]);
  const firstDate = trend.first_date || points[0].date || "";
  const latestDate = trend.latest_date || points[points.length - 1].date || "";
  els.trendReturn.textContent = returnText;
  els.trendReturn.title = "Total return from first weekly close to latest weekly close.";
  els.trendReturn.dataset.direction = Number.isFinite(totalReturn) && totalReturn < 0 ? "down" : "up";
  els.trendRange.textContent = `${shortYear(firstDate)}-${shortYear(latestDate)}`;
  els.trendPrice.textContent = Number.isFinite(latestClose) ? `$${latestClose.toFixed(latestClose >= 100 ? 0 : 2)}` : "-";
  els.trendChartBody.innerHTML = `
    <svg class="trend-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="Lifetime close price trend">
      <defs>
        <linearGradient id="trendLineGradient" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#7db8ff" />
          <stop offset="1" stop-color="#4fd1c5" />
        </linearGradient>
      </defs>
      <polyline class="trend-line" points="${path}" />
    </svg>
  `;
}

function shortYear(value) {
  if (!value) return "-";
  const year = String(value).slice(0, 4);
  return year || "-";
}

function shortTrendError(message) {
  const clean = String(message || "").trim();
  const lower = clean.toLowerCase();
  if (lower.includes("too many requests") || lower.includes("rate limit")) return "Rate limited";
  if (lower.includes("historical candlestick quota") || lower.includes("quota is released")) return "Futu history quota";
  if (lower.includes("possibly delisted") || lower.includes("no yfpricedata")) return "No price history";
  return clean ? clean.slice(0, 32) : "Trend unavailable";
}

function setWatchState(watched) {
  selectedTickerWatched = watched;
  els.detailWatchButton.dataset.watched = watched ? "true" : "false";
  const label = watched ? "Remove from watchlist" : "Add to watchlist";
  els.detailWatchButton.setAttribute("aria-label", label);
  els.detailWatchButton.title = label;
  els.detailWatchButton.textContent = "";
}

async function toggleWatch() {
  if (!selectedTicker) return;
  els.detailWatchButton.disabled = true;
  try {
    if (selectedTickerWatched) {
      await api(`/api/watchlist/${selectedTicker}`, {method: "DELETE"});
    } else {
      await api("/api/watchlist", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ticker: selectedTicker}),
      });
    }
    await refreshWatchlist();
    await loadTickerFuture(selectedTicker);
    await refreshAll();
  } catch (error) {
    alert(error.message);
  } finally {
    els.detailWatchButton.disabled = false;
  }
}

async function rerunTicker() {
  if (!selectedTicker) return;
  const ticker = selectedTicker;
  els.rerunTickerButton.disabled = true;
  els.rerunTickerButton.textContent = "Refetching";
  try {
    await api("/api/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        tickers: ticker,
        screen_mode: "tickers",
        screen_condition: "",
        screen_limit: 1,
        use_futu: true,
        use_sec: true,
        use_yfinance: els.useYfinance.checked,
        use_13f: els.use13f.checked,
        use_usaspending: els.useUsaspending.checked,
        use_launch_library: false,
        use_company_official: false,
        use_openinsider: els.useOpenInsider.checked,
        summarize: els.useMinimax.checked,
        delay_seconds: 1.0,
      }),
    });
    els.detailLastRun.textContent = `Last trigger web · Running · ${formatShortTime(new Date().toISOString())}`;
    await refreshRuns();
  } catch (error) {
    alert(error.message);
  } finally {
    els.rerunTickerButton.disabled = false;
    els.rerunTickerButton.textContent = "Refetch Truth";
  }
}

async function startRun() {
  els.runButton.disabled = true;
  try {
    persistTickerInput();
    await api("/api/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        tickers: els.tickerInput.value,
        screen_mode: els.screenMode.value,
        screen_condition: els.screenCondition.value,
        screen_limit: 50,
        use_futu: els.useFutuScreen.checked,
        use_sec: els.useSec.checked,
        use_yfinance: els.useYfinance.checked,
        use_13f: els.use13f.checked,
        use_usaspending: els.useUsaspending.checked,
        use_launch_library: els.useLaunchLibrary.checked,
        use_company_official: els.useCompanyOfficial.checked,
        use_openinsider: els.useOpenInsider.checked,
        summarize: els.useMinimax.checked,
        delay_seconds: 1.0,
      }),
    });
    closeScreeningDialog();
    await refreshRuns();
  } catch (error) {
    alert(error.message);
  } finally {
    els.runButton.disabled = false;
  }
}

async function generateSummary() {
  if (!selectedTicker) return;
  const ticker = selectedTicker;
  els.summaryButton.disabled = true;
  els.summaryButton.textContent = "Writing";
  els.summaryMeta.textContent = "LLM is summarizing";
  try {
    const data = await api(`/api/ticker/${ticker}/summary`, {method: "POST"});
    if (ticker !== selectedTicker) return;
    renderCompanySummary(data.summary);
    if (els.dimensionFilter.value === "company_summary") await loadTicker(ticker);
  } catch (error) {
    els.summaryBody.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  } finally {
    els.summaryButton.disabled = false;
    if (ticker === selectedTicker && els.summaryButton.textContent === "Writing") {
      els.summaryButton.textContent = "Regenerate";
    }
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function tickerKey(item) {
  return String(item.ticker || "").toUpperCase();
}

function hydrateTickerInput() {
  const savedTickers = localStorage.getItem(TICKER_STORAGE_KEY) || localStorage.getItem(LEGACY_TICKER_STORAGE_KEY);
  els.tickerInput.value = savedTickers || "";
}

function persistTickerInput() {
  localStorage.setItem(TICKER_STORAGE_KEY, els.tickerInput.value.trim());
}

function scheduleCandidateRefresh() {
  window.clearTimeout(candidateSearchTimer);
  candidateSearchTimer = window.setTimeout(refreshAll, CANDIDATE_SEARCH_DEBOUNCE_MS);
}

function syncSearchInput(source) {
  const value = source.value;
  if (source === els.globalSearch) {
    els.candidateSearch.value = value;
  } else {
    els.globalSearch.value = value;
  }
  scheduleCandidateRefresh();
}

function submitSearchInput(source) {
  if (source === els.globalSearch) {
    els.candidateSearch.value = source.value;
  } else {
    els.globalSearch.value = source.value;
  }
  window.clearTimeout(candidateSearchTimer);
  refreshAll();
}

function focusPanel(selector, target) {
  document.querySelector(selector)?.scrollIntoView({behavior: "smooth", block: "start"});
  if (target) window.setTimeout(() => target.focus({preventScroll: true}), 200);
}

function openScreeningDialog() {
  showWorkspaceView("screening");
  if (typeof els.screeningDialog.showModal === "function") {
    els.screeningDialog.showModal();
  } else {
    els.screeningDialog.setAttribute("open", "");
  }
}

function closeScreeningDialog() {
  if (typeof els.screeningDialog.close === "function") {
    els.screeningDialog.close();
  } else {
    els.screeningDialog.removeAttribute("open");
  }
}

function openQueueDrawer() {
  els.queueDrawer.classList.add("open");
  els.queueDrawer.setAttribute("aria-hidden", "false");
  els.workerState.setAttribute("aria-expanded", "true");
  els.latestRun.setAttribute("aria-expanded", "true");
}

function closeQueueDrawer() {
  els.queueDrawer.classList.remove("open");
  els.queueDrawer.setAttribute("aria-hidden", "true");
  els.workerState.setAttribute("aria-expanded", "false");
  els.latestRun.setAttribute("aria-expanded", "false");
}

els.openScreeningButton.addEventListener("click", openScreeningDialog);
els.navPoolsButton.addEventListener("click", async () => {
  await showWorkspaceView("research");
  focusPanel(".candidates", els.candidateSearch);
});
els.navDetailsButton.addEventListener("click", async () => {
  await showWorkspaceView("details");
  focusPanel(".detail", els.rerunTickerButton);
});
els.navOpeningRadarButton.addEventListener("click", () => showWorkspaceView("opening-radar"));
els.navDataSourcesButton.addEventListener("click", () => showWorkspaceView("datasources"));
els.openRunsButton.addEventListener("click", openQueueDrawer);
els.closeScreeningDialog.addEventListener("click", closeScreeningDialog);
els.runButton.addEventListener("click", startRun);
els.summaryButton.addEventListener("click", generateSummary);
els.refreshButton.addEventListener("click", refreshAll);
els.refreshOpeningRadarButton.addEventListener("click", () => loadOpeningRadar({force: true}));
els.generateOpeningAdviceButton.addEventListener("click", generateOpeningAdvice);
els.detailWatchButton.addEventListener("click", toggleWatch);
els.rerunTickerButton.addEventListener("click", rerunTicker);
els.refreshTimetableButton.addEventListener("click", refreshTimetableSources);
els.summaryTab.addEventListener("click", () => setDetailTab("summary"));
els.truthTab.addEventListener("click", () => setDetailTab("truth"));
els.timetableTab.addEventListener("click", () => setDetailTab("timetable"));
els.chartTab.addEventListener("click", () => setDetailTab("chart"));
els.workerState.addEventListener("click", openQueueDrawer);
els.latestRun.addEventListener("click", openQueueDrawer);
els.queueClose.addEventListener("click", closeQueueDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeQueueDrawer();
    if (els.screeningDialog.open) closeScreeningDialog();
  }
});
els.tickerInput.addEventListener("input", persistTickerInput);
els.globalSearch.addEventListener("input", () => syncSearchInput(els.globalSearch));
els.globalSearch.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  submitSearchInput(els.globalSearch);
});
els.candidateSearch.addEventListener("input", () => syncSearchInput(els.candidateSearch));
els.candidateSearch.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  submitSearchInput(els.candidateSearch);
});
els.sectorFilter.addEventListener("change", refreshAll);
els.minScore.addEventListener("change", refreshAll);
els.perSector.addEventListener("change", refreshAll);
els.dimensionFilter.addEventListener("change", () => selectedTicker && loadTicker(selectedTicker));

hydrateTickerInput();
showWorkspaceView("research");
setDetailTab("summary");
refreshAll();
setInterval(refreshRuns, 4000);

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
let shortTermTracking = false;
let shortTermTicker = null;
let shortTermTimer = null;
let shortTermUnloadSent = false;
let openingRadarLoaded = false;
let openingRadarSnapshot = null;
let openingRadarReportId = null;
let activeSectorRadar = "space";
let activeOpeningRadarSubView = "today";
let openingTrendCache = new Map();
let openingTrendRequest = 0;
let openingTrendData = null;
let tradingLoaded = false;
let tradingStrategies = [];
let tradingPairs = [];
let tradingInstances = [];
let activeTradingInstanceId = null;
let tradingRefreshTimer = null;
let tradingDetailRequest = 0;
let tradingBacktestRequest = 0;
let tradingDetailView = "live";
let latestTradingDetail = null;
let tradingBacktestResult = null;
let tradingBacktestSelectedDate = null;
const tradingChartStore = new Map();

const TICKER_STORAGE_KEY = "codeBeta.tickers";
const LEGACY_TICKER_STORAGE_KEY = "hiddenChampionScreener.tickers";
const CANDIDATE_SEARCH_DEBOUNCE_MS = 250;
const SHORT_TERM_POLL_MS = 1000;
const TRADING_UI_POLL_MS = 2000;
const TRADING_CHART_COLORS = {
  bg: "#070a0f",
  panel: "#0d131a",
  grid: "rgba(154, 168, 182, 0.13)",
  axis: "rgba(154, 168, 182, 0.28)",
  muted: "#8492a5",
  text: "#dbe5ee",
  long: "#7db8ff",
  short: "#f5bd4f",
  rsi: "#4fd1c5",
  buy: "#52d273",
  sell: "#ff6b7a",
};

const els = {
  openScreeningButton: document.querySelector("#openScreeningButton"),
  navPoolsButton: document.querySelector("#navPoolsButton"),
  navDetailsButton: document.querySelector("#navDetailsButton"),
  navOpeningRadarButton: document.querySelector("#navOpeningRadarButton"),
  navOpeningTodayButton: document.querySelector("#navOpeningTodayButton"),
  navOpeningTrendButton: document.querySelector("#navOpeningTrendButton"),
  navTradingButton: document.querySelector("#navTradingButton"),
  navTradingSimulateButton: document.querySelector("#navTradingSimulateButton"),
  navTradingRealButton: document.querySelector("#navTradingRealButton"),
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
  openingTodayTab: document.querySelector("#openingTodayTab"),
  openingLongTermTab: document.querySelector("#openingLongTermTab"),
  openingTodayPanel: document.querySelector("#openingTodayPanel"),
  openingTrendPanel: document.querySelector("#openingTrendPanel"),
  openingTrendIndex: document.querySelector("#openingTrendIndex"),
  openingTrendTransform: document.querySelector("#openingTrendTransform"),
  refreshOpeningTrendButton: document.querySelector("#refreshOpeningTrendButton"),
  openingTrendStatus: document.querySelector("#openingTrendStatus"),
  openingTrendKicker: document.querySelector("#openingTrendKicker"),
  openingTrendTitle: document.querySelector("#openingTrendTitle"),
  openingTrendLatest: document.querySelector("#openingTrendLatest"),
  openingTrendChart: document.querySelector("#openingTrendChart"),
  openingTrendRange: document.querySelector("#openingTrendRange"),
  openingTrendSource: document.querySelector("#openingTrendSource"),
  openingTrendStats: document.querySelector("#openingTrendStats"),
  openingTrendExplain: document.querySelector("#openingTrendExplain"),
  analyzeOpeningTrendButton: document.querySelector("#analyzeOpeningTrendButton"),
  openingTrendAnalysisMeta: document.querySelector("#openingTrendAnalysisMeta"),
  openingTrendAnalysisBody: document.querySelector("#openingTrendAnalysisBody"),
  openingRadarPrimary: document.querySelector("#openingRadarPrimary"),
  sectorRadarTabs: document.querySelector("#sectorRadarTabs"),
  sectorRadarPanel: document.querySelector("#sectorRadarPanel"),
  openingAdviceMeta: document.querySelector("#openingAdviceMeta"),
  openingReportHistory: document.querySelector("#openingReportHistory"),
  openingAdviceBody: document.querySelector("#openingAdviceBody"),
  tradingPage: document.querySelector("#tradingPage"),
  tradingStatus: document.querySelector("#tradingStatus"),
  toggleTradingFocusButton: document.querySelector("#toggleTradingFocusButton"),
  refreshTradingButton: document.querySelector("#refreshTradingButton"),
  tradingNameInput: document.querySelector("#tradingNameInput"),
  tradingPairSelect: document.querySelector("#tradingPairSelect"),
  tradingSignalTickerInput: document.querySelector("#tradingSignalTickerInput"),
  tradingLongTickerInput: document.querySelector("#tradingLongTickerInput"),
  tradingShortTickerInput: document.querySelector("#tradingShortTickerInput"),
  tradingNotionalInput: document.querySelector("#tradingNotionalInput"),
  tradingPollSecondsInput: document.querySelector("#tradingPollSecondsInput"),
  createTradingInstanceButton: document.querySelector("#createTradingInstanceButton"),
  tradingInstanceList: document.querySelector("#tradingInstanceList"),
  tradingActiveMode: document.querySelector("#tradingActiveMode"),
  tradingActiveName: document.querySelector("#tradingActiveName"),
  tradingActiveMeta: document.querySelector("#tradingActiveMeta"),
  startTradingInstanceButton: document.querySelector("#startTradingInstanceButton"),
  stopTradingInstanceButton: document.querySelector("#stopTradingInstanceButton"),
  deleteTradingInstanceButton: document.querySelector("#deleteTradingInstanceButton"),
  tradingEmptyState: document.querySelector("#tradingEmptyState"),
  tradingDetailBody: document.querySelector("#tradingDetailBody"),
  tradingDetailStrategySelect: document.querySelector("#tradingDetailStrategySelect"),
  tradingDetailProfitTakeInput: document.querySelector("#tradingDetailProfitTakeInput"),
  tradingStrategyLabel: document.querySelector("#tradingStrategyLabel"),
  tradingStrategyDescription: document.querySelector("#tradingStrategyDescription"),
  tradingStrategySaveState: document.querySelector("#tradingStrategySaveState"),
  tradingStrategyRules: document.querySelector("#tradingStrategyRules"),
  tradingStrategyPerformance: document.querySelector("#tradingStrategyPerformance"),
  tradingLiveTab: document.querySelector("#tradingLiveTab"),
  tradingBacktestTab: document.querySelector("#tradingBacktestTab"),
  tradingLivePanel: document.querySelector("#tradingLivePanel"),
  tradingBacktestPanel: document.querySelector("#tradingBacktestPanel"),
  tradingStrategyState: document.querySelector("#tradingStrategyState"),
  tradingMetricGrid: document.querySelector("#tradingMetricGrid"),
  tradingQuoteStrip: document.querySelector("#tradingQuoteStrip"),
  tradingPositionGrid: document.querySelector("#tradingPositionGrid"),
  tradingPriceMeta: document.querySelector("#tradingPriceMeta"),
  tradingRsiMeta: document.querySelector("#tradingRsiMeta"),
  tradingPriceChart: document.querySelector("#tradingPriceChart"),
  tradingRsiChart: document.querySelector("#tradingRsiChart"),
  tradingEventCount: document.querySelector("#tradingEventCount"),
  tradingTradeCount: document.querySelector("#tradingTradeCount"),
  tradingEventLog: document.querySelector("#tradingEventLog"),
  tradingTradeLog: document.querySelector("#tradingTradeLog"),
  tradingBacktestStart: document.querySelector("#tradingBacktestStart"),
  tradingBacktestEnd: document.querySelector("#tradingBacktestEnd"),
  runTradingBacktestButton: document.querySelector("#runTradingBacktestButton"),
  tradingBacktestMoreButton: document.querySelector("#tradingBacktestMoreButton"),
  tradingBacktestPeriodSummary: document.querySelector("#tradingBacktestPeriodSummary"),
  tradingBacktestPeriodDetails: document.querySelector("#tradingBacktestPeriodDetails"),
  tradingBacktestDailySection: document.querySelector("#tradingBacktestDailySection"),
  tradingBacktestDailyCount: document.querySelector("#tradingBacktestDailyCount"),
  tradingBacktestDailyList: document.querySelector("#tradingBacktestDailyList"),
  tradingBacktestDayDetail: document.querySelector("#tradingBacktestDayDetail"),
  tradingBacktestSelectedDate: document.querySelector("#tradingBacktestSelectedDate"),
  tradingBacktestSelectedOutcome: document.querySelector("#tradingBacktestSelectedOutcome"),
  tradingBacktestSummary: document.querySelector("#tradingBacktestSummary"),
  tradingBacktestDayFacts: document.querySelector("#tradingBacktestDayFacts"),
  tradingBacktestPriceMeta: document.querySelector("#tradingBacktestPriceMeta"),
  tradingBacktestPriceChart: document.querySelector("#tradingBacktestPriceChart"),
  tradingBacktestRsiMeta: document.querySelector("#tradingBacktestRsiMeta"),
  tradingBacktestRsiChart: document.querySelector("#tradingBacktestRsiChart"),
  tradingBacktestOperations: document.querySelector("#tradingBacktestOperations"),
  tradingBacktestOperationCount: document.querySelector("#tradingBacktestOperationCount"),
  tradingBacktestTrades: document.querySelector("#tradingBacktestTrades"),
  tradingBacktestTradeCount: document.querySelector("#tradingBacktestTradeCount"),
  tradingBacktestAudit: document.querySelector("#tradingBacktestAudit"),
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
  shortTermTab: document.querySelector("#shortTermTab"),
  chartTab: document.querySelector("#chartTab"),
  summaryPanel: document.querySelector("#summaryPanel"),
  truthPanel: document.querySelector("#truthPanel"),
  timetablePanel: document.querySelector("#timetablePanel"),
  shortTermPanel: document.querySelector("#shortTermPanel"),
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
  shortTermStatus: document.querySelector("#shortTermStatus"),
  shortTermWindow: document.querySelector("#shortTermWindow"),
  shortTermTrackButton: document.querySelector("#shortTermTrackButton"),
  shortTermDecision: document.querySelector("#shortTermDecision"),
  shortTermRules: document.querySelector("#shortTermRules"),
  shortTermMetrics: document.querySelector("#shortTermMetrics"),
  shortTermChart: document.querySelector("#shortTermChart"),
  shortTermTape: document.querySelector("#shortTermTape"),
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
  const tradingView = view === "trading-simulate";
  els.researchGrid.hidden = datasourceView || openingRadarView || tradingView;
  els.datasourcePage.hidden = !datasourceView;
  els.openingRadarPage.hidden = !openingRadarView;
  els.tradingPage.hidden = !tradingView;
  els.openScreeningButton.classList.toggle("active", view === "screening");
  els.navOpeningRadarButton.classList.toggle("active", openingRadarView);
  els.navTradingButton.classList.toggle("active", tradingView);
  els.navTradingSimulateButton.classList.toggle("active", tradingView);
  els.navPoolsButton.classList.toggle("active", view === "research");
  els.navDetailsButton.classList.toggle("active", view === "details");
  els.navDataSourcesButton.classList.toggle("active", datasourceView);
  els.navTradingButton.setAttribute("aria-expanded", tradingView ? "true" : "false");
  window.clearTimeout(tradingRefreshTimer);
  if (datasourceView) await loadDataSources();
  if (openingRadarView) {
    renderOpeningRadarSubView();
    if (activeOpeningRadarSubView === "trend") {
      await loadOpeningLongTermTrend();
    } else {
      await loadOpeningRadar();
    }
  }
  if (tradingView) {
    await loadTradingSimulate();
    scheduleTradingRefresh();
  } else {
    setTradingFocusMode(false);
  }
}

function setTradingFocusMode(enabled) {
  document.body.classList.toggle("trading-focus-mode", Boolean(enabled));
  if (els.toggleTradingFocusButton) {
    els.toggleTradingFocusButton.textContent = enabled ? "Exit Focus" : "Focus";
    els.toggleTradingFocusButton.setAttribute("aria-pressed", enabled ? "true" : "false");
  }
  window.setTimeout(scheduleTradingChartResize, 80);
}

function toggleTradingFocusMode() {
  setTradingFocusMode(!document.body.classList.contains("trading-focus-mode"));
}

async function openOpeningRadarView(subView = "today") {
  activeOpeningRadarSubView = subView === "trend" ? "trend" : "today";
  await showWorkspaceView("opening-radar");
}

async function setOpeningRadarSubView(subView) {
  activeOpeningRadarSubView = subView === "trend" ? "trend" : "today";
  renderOpeningRadarSubView();
  if (activeWorkspaceView !== "opening-radar") return;
  if (activeOpeningRadarSubView === "trend") {
    await loadOpeningLongTermTrend();
  } else {
    await loadOpeningRadar();
  }
}

function renderOpeningRadarSubView() {
  const trendActive = activeOpeningRadarSubView === "trend";
  els.openingTodayTab.classList.toggle("active", !trendActive);
  els.openingLongTermTab.classList.toggle("active", trendActive);
  els.openingTodayPanel.hidden = trendActive;
  els.openingTrendPanel.hidden = !trendActive;
  els.refreshOpeningRadarButton.hidden = trendActive;
  els.generateOpeningAdviceButton.hidden = trendActive;
  els.navOpeningTodayButton.classList.toggle("active", !trendActive);
  els.navOpeningTrendButton.classList.toggle("active", trendActive);
  els.navOpeningRadarButton.setAttribute("aria-expanded", trendActive ? "true" : "false");
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

async function loadOpeningLongTermTrend({force = false} = {}) {
  const indexKey = els.openingTrendIndex.value || "nasdaq";
  const transform = els.openingTrendTransform.value || "raw";
  const cacheKey = `${indexKey}:${transform}`;
  const requestId = ++openingTrendRequest;
  if (!force && openingTrendCache.has(cacheKey)) {
    renderOpeningLongTermTrend(openingTrendCache.get(cacheKey));
    return;
  }
  els.openingTrendStatus.textContent = "Loading long term history";
  els.openingTrendChart.innerHTML = `<div class="empty">Loading long term trend</div>`;
  resetOpeningTrendAnalysis();
  try {
    const data = await api(`/api/opening-radar/long-term-trend?index=${encodeURIComponent(indexKey)}&transform=${encodeURIComponent(transform)}&max_points=760`);
    if (requestId !== openingTrendRequest) return;
    openingTrendCache.set(cacheKey, data);
    renderOpeningLongTermTrend(data);
  } catch (error) {
    if (requestId !== openingTrendRequest) return;
    els.openingTrendStatus.textContent = "Trend unavailable";
    els.openingTrendChart.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    els.openingTrendStats.innerHTML = "";
  }
}

function renderOpeningLongTermTrend(data) {
  openingTrendData = data;
  const points = Array.isArray(data.points) ? data.points.filter((point) => Number.isFinite(Number(point.value))) : [];
  const transform = data.transform || {};
  const transformKey = transform.key || els.openingTrendTransform.value || "raw";
  els.openingTrendKicker.textContent = transform.label || "Long Term Trend";
  els.openingTrendTitle.textContent = data.label || data.symbol || "Index";
  els.openingTrendStatus.textContent = data.latest_date
    ? `${data.symbol || ""} · Updated ${data.latest_date}`
    : data.error || "No data";
  els.openingTrendSource.textContent = data.source_label || data.source || "-";
  els.openingTrendRange.textContent = data.first_date && data.latest_date ? `${shortYear(data.first_date)}-${shortYear(data.latest_date)}` : "-";
  if (data.error || points.length < 2) {
    els.openingTrendLatest.textContent = "-";
    els.openingTrendChart.innerHTML = `<div class="empty">${escapeHtml(data.error || "Not enough long term history")}</div>`;
    els.openingTrendStats.innerHTML = "";
    els.analyzeOpeningTrendButton.disabled = true;
    return;
  }
  els.analyzeOpeningTrendButton.disabled = false;
  const latest = points[points.length - 1];
  els.openingTrendLatest.textContent = trendValueText(latest.value, transformKey);
  els.openingTrendChart.innerHTML = openingTrendSvg(points, transformKey);
  renderOpeningTrendStats(data, latest.value, transformKey);
  renderOpeningTrendExplain(data);
}

function openingTrendSvg(points, transformKey) {
  const width = 980;
  const height = 430;
  const padTop = 22;
  const padRight = 18;
  const padBottom = 42;
  const padLeft = 18;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  const values = points.map((point) => Number(point.value));
  const [minValue, maxValue] = openingTrendDisplayDomain(values, transformKey);
  const span = maxValue - minValue || Math.max(Math.abs(maxValue), 1);
  const lastIndex = points.length - 1;
  const path = points
    .map((point, index) => {
      const x = padLeft + (index / lastIndex) * plotWidth;
      const clampedValue = clamp(Number(point.value), minValue, maxValue);
      const y = padTop + (1 - (clampedValue - minValue) / span) * plotHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const gridYs = [0.25, 0.5, 0.75]
    .map((ratio) => {
      const y = padTop + ratio * plotHeight;
      return `<line class="opening-trend-grid-line" x1="${padLeft}" x2="${width - padRight}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" />`;
    })
    .join("");
  const axisY = height - padBottom + 12;
  const tickCount = Math.min(6, points.length);
  const xTicks = Array.from({length: tickCount}, (_, tickIndex) => {
    const pointIndex = tickCount === 1 ? 0 : Math.round((tickIndex / (tickCount - 1)) * lastIndex);
    const point = points[pointIndex] || {};
    const x = padLeft + (pointIndex / lastIndex) * plotWidth;
    const label = shortYear(point.date || point.as_of || point.timestamp || "");
    if (!label) return "";
    const anchor = tickIndex === 0 ? "start" : tickIndex === tickCount - 1 ? "end" : "middle";
    return `
      <line class="opening-trend-axis-tick" x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${axisY - 5}" y2="${axisY}" />
      <text class="opening-trend-axis-label" x="${x.toFixed(1)}" y="${axisY + 16}" text-anchor="${anchor}">${escapeHtml(label)}</text>
    `;
  }).join("");
  let zeroLine = "";
  if (transformKey === "detrended" && minValue < 0 && maxValue > 0) {
    const y = padTop + (1 - (0 - minValue) / span) * plotHeight;
    zeroLine = `<line class="opening-trend-zero-line" x1="${padLeft}" x2="${width - padRight}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" />`;
  }
  return `
    <svg class="opening-trend-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="Long term index trend">
      ${gridYs}
      ${zeroLine}
      <polyline class="opening-trend-line" points="${path}" />
      <line class="opening-trend-axis-line" x1="${padLeft}" x2="${width - padRight}" y1="${axisY}" y2="${axisY}" />
      ${xTicks}
    </svg>
  `;
}

function openingTrendDisplayDomain(values, transformKey) {
  const finiteValues = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!finiteValues.length) return [0, 1];
  const rawMin = finiteValues[0];
  const rawMax = finiteValues[finiteValues.length - 1];
  return paddedDomain(rawMin, rawMax);
}

function paddedDomain(minValue, maxValue) {
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) return [0, 1];
  const span = maxValue - minValue;
  if (span === 0) {
    const pad = Math.max(Math.abs(maxValue) * 0.1, 1);
    return [minValue - pad, maxValue + pad];
  }
  const pad = span * 0.08;
  return [minValue - pad, maxValue + pad];
}

function quantile(sortedValues, ratio) {
  if (!sortedValues.length) return NaN;
  const index = (sortedValues.length - 1) * ratio;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sortedValues[lower];
  const weight = index - lower;
  return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
}

function clamp(value, minValue, maxValue) {
  if (!Number.isFinite(value)) return minValue;
  return Math.min(Math.max(value, minValue), maxValue);
}

function renderOpeningTrendStats(data, latestValue, transformKey) {
  const stats = [
    ["Latest", trendValueText(latestValue, transformKey), data.latest_date || "-"],
    ["Total", pctText(data.total_return), "raw return"],
    ["CAGR", pctText(data.cagr), "annualized"],
    ["Points", String(data.point_count || 0), data.period || "max"],
  ];
  if (transformKey === "detrended") {
    stats.splice(1, 0, ["Gap", trendValueText(latestValue, transformKey), "vs log trend"]);
  }
  els.openingTrendStats.innerHTML = stats
    .map(
      ([label, value, help]) => `
        <div class="opening-trend-stat">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(help || "")}</small>
        </div>
      `
    )
    .join("");
}

function renderOpeningTrendExplain(data) {
  const transform = data.transform || {};
  const text = transform.explanation_zh || "对长期指数做数学变换，帮助把复利增长和估值偏离分开看。";
  els.openingTrendExplain.innerHTML = `
    <strong>How to read</strong>
    <p>${escapeHtml(text)}</p>
  `;
}

function resetOpeningTrendAnalysis() {
  if (!els.openingTrendAnalysisMeta || !els.openingTrendAnalysisBody) return;
  els.openingTrendAnalysisMeta.textContent = "Manual analyze";
  els.openingTrendAnalysisBody.innerHTML = `<div class="empty">Analyze current trend points for risk and opportunity.</div>`;
}

async function analyzeOpeningTrend() {
  els.analyzeOpeningTrendButton.disabled = true;
  els.analyzeOpeningTrendButton.textContent = "Thinking";
  els.openingTrendAnalysisMeta.textContent = "MiniMax running";
  els.openingTrendAnalysisBody.innerHTML = `<div class="empty">Analyzing current trend points</div>`;
  try {
    if (!openingTrendData || openingTrendData.error) {
      await loadOpeningLongTermTrend({force: false});
    }
    const data = await api("/api/opening-radar/long-term-trend/analyze", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        index: els.openingTrendIndex.value || "nasdaq",
        transform: els.openingTrendTransform.value || "raw",
      }),
    });
    renderOpeningTrendAnalysis(data);
  } catch (error) {
    els.openingTrendAnalysisMeta.textContent = "Failed";
    els.openingTrendAnalysisBody.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  } finally {
    els.analyzeOpeningTrendButton.disabled = false;
    els.analyzeOpeningTrendButton.textContent = "Analyze";
  }
}

function renderOpeningTrendAnalysis(data) {
  const analysis = data.analysis || data;
  els.openingTrendAnalysisMeta.textContent = `${escapeHtml(data.provider || analysis.provider || "MiniMax")} · C ${Number(analysis.confidence_score || 0).toFixed(0)}`;
  els.openingTrendAnalysisBody.innerHTML = `
    <section class="advice-block wide">
      <h3>Current Read</h3>
      <p>${escapeHtml(analysis.current_read || analysis.summary || "No analysis returned.")}</p>
    </section>
    ${adviceList("Risks", analysis.risks)}
    ${adviceList("Opportunities", analysis.opportunities)}
    ${adviceList("Watch Levels", analysis.watch_levels)}
    ${adviceList("Action Notes", analysis.action_notes)}
  `;
}

function trendValueText(value, transformKey) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (transformKey === "detrended") return pctText(number);
  if (transformKey === "log") return number.toFixed(2);
  return number >= 1000 ? number.toFixed(0) : number.toFixed(2);
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
  if (number >= 70) return "超买";
  if (number <= 30) return "超卖";
  if (number >= 55) return "偏强区";
  if (number <= 45) return "偏弱区";
  return "中性";
}

function kdjLabel(indicators) {
  const k = Number(indicators.kdj_k);
  const d = Number(indicators.kdj_d);
  if (!Number.isFinite(k) || !Number.isFinite(d)) return "-";
  if (k > 80) return "过热";
  if (k < 20) return "过冷";
  return k > d ? "拐头向上" : "拐头向下";
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

async function loadTradingSimulate({force = false} = {}) {
  if (!tradingLoaded || force) {
    try {
      const data = await api("/api/trading/simulate/strategies");
      tradingStrategies = data.strategies || [];
      tradingPairs = data.pairs || [];
      renderTradingStrategyOptions();
      renderTradingPairOptions();
      tradingLoaded = true;
    } catch (error) {
      els.tradingStatus.textContent = error.message;
    }
  }
  await refreshTradingInstances();
}

function renderTradingStrategyOptions(selectedStrategyId = null, instance = latestTradingDetail) {
  const current = selectedStrategyId || els.tradingDetailStrategySelect.value || "rsi_extreme";
  const performance = instance?.strategy_performance || {};
  els.tradingDetailStrategySelect.innerHTML = "";
  for (const strategy of tradingStrategies) {
    const option = document.createElement("option");
    option.value = strategy.id;
    option.textContent = strategyOptionText(strategy, performance[strategy.id]);
    els.tradingDetailStrategySelect.appendChild(option);
  }
  if (!tradingStrategies.length) {
    const option = document.createElement("option");
    option.value = "rsi_extreme";
    option.textContent = "RSI Extreme";
    els.tradingDetailStrategySelect.appendChild(option);
  }
  els.tradingDetailStrategySelect.value = [...els.tradingDetailStrategySelect.options].some((option) => option.value === current)
    ? current
    : els.tradingDetailStrategySelect.options[0]?.value || "rsi_extreme";
}

async function refreshTradingInstances() {
  try {
    const data = await api("/api/trading/simulate/instances");
    tradingInstances = data.instances || [];
    if (!tradingStrategies.length && data.strategies) {
      tradingStrategies = data.strategies;
      renderTradingStrategyOptions();
    }
    if (!tradingPairs.length && data.pairs) {
      tradingPairs = data.pairs;
      renderTradingPairOptions();
    }
    if (activeTradingInstanceId && !tradingInstances.some((item) => item.id === activeTradingInstanceId)) {
      activeTradingInstanceId = null;
    }
    if (!activeTradingInstanceId && tradingInstances.length) {
      activeTradingInstanceId = tradingInstances[0].id;
    }
    renderTradingInstanceList();
    if (activeTradingInstanceId) {
      await loadTradingInstanceDetail(activeTradingInstanceId);
    } else {
      clearTradingDetail();
    }
  } catch (error) {
    els.tradingStatus.textContent = error.message;
  }
}

async function loadTradingInstanceDetail(instanceId) {
  const requestId = ++tradingDetailRequest;
  try {
    const data = await api(`/api/trading/simulate/instances/${encodeURIComponent(instanceId)}`);
    if (requestId !== tradingDetailRequest) return;
    renderTradingDetail(data.instance);
  } catch (error) {
    if (requestId !== tradingDetailRequest) return;
    els.tradingStatus.textContent = error.message;
    clearTradingDetail();
  }
}

function scheduleTradingRefresh() {
  window.clearTimeout(tradingRefreshTimer);
  if (activeWorkspaceView !== "trading-simulate") return;
  tradingRefreshTimer = window.setTimeout(async () => {
    await refreshTradingInstances();
    scheduleTradingRefresh();
  }, TRADING_UI_POLL_MS);
}

function renderTradingInstanceList() {
  els.tradingInstanceList.innerHTML = "";
  if (!tradingInstances.length) {
    els.tradingInstanceList.innerHTML = `<div class="empty">No instances</div>`;
    return;
  }
  for (const instance of tradingInstances) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `trading-instance-card${instance.id === activeTradingInstanceId ? " active" : ""}`;
    const pnl = Number(instance.total_pnl || 0);
    button.innerHTML = `
      <strong>${escapeHtml(instance.name || `${instance.long_ticker}/${instance.short_ticker}`)}</strong>
      <span>${escapeHtml(instance.signal_ticker || "-")} signal · ${escapeHtml(instance.long_ticker || "-")} long / ${escapeHtml(instance.short_ticker || "-")} bear</span>
      <small data-pnl="${pnlDirection(pnl)}">${escapeHtml(tradingStatusText(instance.status))} · ${escapeHtml(moneyText(pnl))} · ${Number(instance.trade_count || 0)} closed</small>
    `;
    button.addEventListener("click", async () => {
      activeTradingInstanceId = instance.id;
      renderTradingInstanceList();
      await loadTradingInstanceDetail(instance.id);
    });
    els.tradingInstanceList.appendChild(button);
  }
}

function renderTradingPairOptions() {
  const current = els.tradingPairSelect.value || "custom";
  els.tradingPairSelect.innerHTML = `<option value="custom">Custom Pair</option>`;
  for (const pair of tradingPairs) {
    const option = document.createElement("option");
    option.value = pair.id;
    option.textContent = pair.label || `${pair.signal_ticker}/${pair.long_ticker}/${pair.short_ticker}`;
    els.tradingPairSelect.appendChild(option);
  }
  els.tradingPairSelect.value = [...els.tradingPairSelect.options].some((option) => option.value === current)
    ? current
    : "custom";
}

function applyTradingPairSelection() {
  const pairId = els.tradingPairSelect.value || "custom";
  const pair = tradingPairs.find((item) => item.id === pairId);
  if (!pair) return;
  els.tradingSignalTickerInput.value = pair.signal_ticker || "";
  els.tradingLongTickerInput.value = pair.long_ticker || "";
  els.tradingShortTickerInput.value = pair.short_ticker || "";
  if (!els.tradingNameInput.value.trim()) {
    els.tradingNameInput.value = pair.label
      ? pair.label
      : `${pair.long_ticker}/${pair.short_ticker}`;
  }
}

function setTradingPairCustom() {
  if (els.tradingPairSelect.value !== "custom") els.tradingPairSelect.value = "custom";
}

function clearTradingDetail() {
  latestTradingDetail = null;
  tradingBacktestResult = null;
  tradingBacktestSelectedDate = null;
  els.tradingStatus.textContent = "Sim only";
  els.tradingActiveMode.textContent = "SIMULATE";
  els.tradingActiveName.textContent = "No instance";
  els.tradingActiveMeta.textContent = "Create or select an instance";
  els.startTradingInstanceButton.disabled = true;
  els.stopTradingInstanceButton.disabled = true;
  els.deleteTradingInstanceButton.disabled = true;
  els.tradingDetailStrategySelect.disabled = true;
  els.tradingDetailProfitTakeInput.disabled = true;
  els.tradingStrategySaveState.textContent = "Select a pair";
  els.tradingEmptyState.hidden = false;
  els.tradingDetailBody.hidden = true;
  renderTradingBacktestEmpty();
}

function renderTradingDetail(instance) {
  if (!instance) {
    clearTradingDetail();
    return;
  }
  const previousId = latestTradingDetail?.id || null;
  latestTradingDetail = instance;
  if (previousId && previousId !== instance.id) {
    tradingBacktestResult = null;
    tradingBacktestSelectedDate = null;
  }
  const running = instance.status === "running";
  const latest = instance.latest_market || {};
  const metrics = instance.metrics || {};
  els.tradingStatus.textContent = running
    ? `Running · ${latest.source_label || "market data"}`
    : instance.last_error
      ? instance.last_error
      : latest.time
        ? `Idle · Last ${shortTimeOnly(latest.time)}`
        : "Sim only";
  els.tradingActiveMode.textContent = tradingStatusText(instance.status).toUpperCase();
  els.tradingActiveName.textContent = instance.name || `${instance.long_ticker}/${instance.short_ticker}`;
  els.tradingActiveMeta.textContent = `${instance.long_ticker} long · ${instance.short_ticker} bear · signal ${instance.signal_ticker}`;
  els.startTradingInstanceButton.disabled = running;
  els.stopTradingInstanceButton.disabled = !running;
  els.deleteTradingInstanceButton.disabled = false;
  els.tradingEmptyState.hidden = true;
  els.tradingDetailBody.hidden = false;
  renderTradingStrategyControl(instance);
  setDefaultBacktestRange(instance);
  renderTradingDetailView();
  renderTradingStrategyState(instance.strategy_state || {});
  renderTradingMetrics(instance, metrics, latest);
  renderTradingQuotes(instance, latest);
  renderTradingCharts(instance);
  renderTradingEventLog(instance.events || []);
  renderTradingTradeLog(instance.trades || []);
}

function renderTradingStrategyControl(instance) {
  const strategyId = instance?.strategy_id || "rsi_extreme";
  renderTradingStrategyOptions(strategyId, instance);
  const strategy = tradingStrategies.find((item) => item.id === strategyId) || instance?.strategy || {};
  const params = strategy.params || {};
  const positions = instance?.positions || {};
  const hasOpenPosition = Boolean(positions.long || positions.short);
  const locked = instance?.status === "running" || hasOpenPosition;
  const profitTakeEnabled = params.profit_take_enabled !== false;
  els.tradingStrategyLabel.textContent = strategy.label || strategyName(strategyId);
  els.tradingStrategyDescription.textContent = strategy.description || "Switch strategies here to compare the same ticker pair.";
  renderTradingStrategyRules(strategy);
  renderTradingStrategyPerformance((instance?.strategy_performance || {})[strategyId]);
  els.tradingDetailStrategySelect.disabled = locked;
  els.tradingDetailProfitTakeInput.disabled = locked || !profitTakeEnabled;
  els.tradingDetailProfitTakeInput.value = String(((Number(instance?.profit_take_pct) || 0.04) * 100).toFixed(1));
  els.tradingDetailProfitTakeInput.closest(".mini-field")?.classList.toggle("is-disabled", !profitTakeEnabled);
  els.tradingStrategySaveState.dataset.state = locked ? "locked" : "saved";
  els.tradingStrategySaveState.textContent = instance?.status === "running"
    ? "Stop to switch"
    : hasOpenPosition
      ? "Close position to switch"
      : "Saved";
}

function previewTradingStrategySelection() {
  const strategyId = els.tradingDetailStrategySelect.value || "rsi_extreme";
  const strategy = tradingStrategies.find((item) => item.id === strategyId) || {};
  const profitTakeEnabled = strategy.params?.profit_take_enabled !== false;
  els.tradingStrategyLabel.textContent = strategy.label || strategyName(strategyId);
  els.tradingStrategyDescription.textContent = strategy.description || "Switch strategies here to compare the same ticker pair.";
  renderTradingStrategyRules(strategy);
  renderTradingStrategyPerformance((latestTradingDetail?.strategy_performance || {})[strategyId]);
  els.tradingDetailProfitTakeInput.disabled = !profitTakeEnabled;
  els.tradingDetailProfitTakeInput.closest(".mini-field")?.classList.toggle("is-disabled", !profitTakeEnabled);
}

function strategyOptionText(strategy, performance) {
  const name = strategy.label || strategy.id || "Strategy";
  const buy = String((strategy.buy_conditions || [])[0] || "").replace(/\.$/, "");
  const sell = String((strategy.sell_conditions || [])[0] || "").replace(/\.$/, "");
  const rules = strategy.option_summary || [buy, sell].filter(Boolean).join(" | ");
  const performanceText = performance
    ? `${(Number(performance.day_win_rate || 0) * 100).toFixed(1)}% days/${Number(performance.day_count || 0)} · ${moneyText(performance.total_pnl || 0)}`
    : "not tested";
  return `${name} · ${rules || "See rules"} · ${performanceText}`;
}

function renderTradingStrategyRules(strategy) {
  const groups = [
    ["BUY", strategy.buy_conditions || [], "buy"],
    ["SELL", strategy.sell_conditions || [], "sell"],
    ["RISK", strategy.risk_conditions || [], "risk"],
  ];
  els.tradingStrategyRules.innerHTML = groups
    .filter(([, rules]) => rules.length)
    .map(
      ([label, rules, kind]) => `
        <div class="trading-strategy-rule" data-kind="${escapeAttribute(kind)}">
          <b>${escapeHtml(label)}</b>
          <span>${escapeHtml(rules.join(" "))}</span>
        </div>
      `
    )
    .join("");
}

function renderTradingStrategyPerformance(performance) {
  if (!performance) {
    els.tradingStrategyPerformance.innerHTML = `
      <span class="trading-strategy-no-performance">No backtest saved for this pair and strategy</span>
    `;
    return;
  }
  const period = `${shortDateTime(performance.start)} -> ${shortDateTime(performance.end)}`;
  const values = [
    ["Day Win", `${(Number(performance.day_win_rate || 0) * 100).toFixed(1)}%`, `${Number(performance.winning_days || 0)}W / ${Number(performance.losing_days || 0)}L · ${Number(performance.day_count || 0)} days`],
    ["Trade Win", `${(Number(performance.trade_win_rate || 0) * 100).toFixed(1)}%`, `${Number(performance.trade_count || 0)} trades`],
    ["PnL", moneyText(performance.total_pnl || 0), `${Number(performance.trades_per_day || 0).toFixed(2)} trades/day`],
    ["Period", period || "-", performance.source_label || "-"],
  ];
  els.tradingStrategyPerformance.innerHTML = values
    .map(
      ([label, value, help]) => `
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(help)}</small>
        </div>
      `
    )
    .join("");
}

async function updateTradingStrategySelection() {
  if (!activeTradingInstanceId) return;
  const strategyId = els.tradingDetailStrategySelect.value || "rsi_extreme";
  const profitTakePercent = Number(els.tradingDetailProfitTakeInput.value || 4);
  els.tradingDetailStrategySelect.disabled = true;
  els.tradingDetailProfitTakeInput.disabled = true;
  els.tradingStrategySaveState.dataset.state = "saving";
  els.tradingStrategySaveState.textContent = "Saving";
  try {
    const data = await api(
      `/api/trading/simulate/instances/${encodeURIComponent(activeTradingInstanceId)}/strategy`,
      {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          strategy_id: strategyId,
          profit_take_percent: profitTakePercent,
        }),
      }
    );
    tradingBacktestResult = null;
    tradingBacktestSelectedDate = null;
    renderTradingBacktestEmpty();
    renderTradingDetail(data.instance);
    await refreshTradingInstances();
  } catch (error) {
    alert(error.message);
    await loadTradingInstanceDetail(activeTradingInstanceId);
  }
}

function setTradingDetailView(view) {
  tradingDetailView = view === "backtest" ? "backtest" : "live";
  renderTradingDetailView();
  if (tradingDetailView === "live" && latestTradingDetail) {
    renderTradingCharts(latestTradingDetail);
  }
  window.setTimeout(scheduleTradingChartResize, 80);
}

function renderTradingDetailView() {
  const isBacktest = tradingDetailView === "backtest";
  els.tradingLiveTab.classList.toggle("active", !isBacktest);
  els.tradingBacktestTab.classList.toggle("active", isBacktest);
  els.tradingLiveTab.setAttribute("aria-selected", isBacktest ? "false" : "true");
  els.tradingBacktestTab.setAttribute("aria-selected", isBacktest ? "true" : "false");
  els.tradingLivePanel.hidden = isBacktest;
  els.tradingBacktestPanel.hidden = !isBacktest;
  if (isBacktest && tradingBacktestResult) {
    renderTradingBacktestResult(tradingBacktestResult);
  }
}

function setDefaultBacktestRange(instance) {
  if (!instance || !els.tradingBacktestStart || !els.tradingBacktestEnd) return;
  const currentId = els.tradingBacktestStart.dataset.instanceId || "";
  const hasRange = Boolean(els.tradingBacktestStart.value && els.tradingBacktestEnd.value);
  if (currentId === instance.id && hasRange) return;
  const latest = parseTradingDate(instance.latest_market?.time) || currentNewYorkDate();
  const {start, end} = regularUsSessionRange(latest);
  els.tradingBacktestStart.value = datetimeLocalValue(start);
  els.tradingBacktestEnd.value = datetimeLocalValue(end);
  els.tradingBacktestStart.dataset.instanceId = instance.id || "";
  els.tradingBacktestEnd.dataset.instanceId = instance.id || "";
}

function renderTradingBacktestEmpty(message = "Select a time range and run backtest") {
  tradingBacktestSelectedDate = null;
  closeTradingPopover(document.querySelector("#tradingBacktestPeriodTip"));
  closeTradingPopover(document.querySelector("#tradingBacktestDayTip"));
  if (els.tradingBacktestMoreButton) els.tradingBacktestMoreButton.hidden = true;
  if (els.tradingBacktestPeriodSummary) {
    els.tradingBacktestPeriodSummary.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
  }
  if (els.tradingBacktestPeriodDetails) els.tradingBacktestPeriodDetails.innerHTML = "";
  if (els.tradingBacktestDailySection) els.tradingBacktestDailySection.hidden = true;
  if (els.tradingBacktestDayDetail) els.tradingBacktestDayDetail.hidden = true;
  if (els.tradingBacktestDailyList) els.tradingBacktestDailyList.innerHTML = "";
  if (els.tradingBacktestDailyCount) els.tradingBacktestDailyCount.textContent = "0 days";
  if (els.tradingBacktestSummary) els.tradingBacktestSummary.innerHTML = "";
  if (els.tradingBacktestDayFacts) els.tradingBacktestDayFacts.innerHTML = "";
  if (els.tradingBacktestAudit) els.tradingBacktestAudit.open = false;
  if (els.tradingBacktestPriceMeta) els.tradingBacktestPriceMeta.textContent = "-";
  if (els.tradingBacktestRsiMeta) els.tradingBacktestRsiMeta.textContent = "-";
  if (els.tradingBacktestPriceChart) {
    renderTradingEmptyChart(els.tradingBacktestPriceChart, "Run backtest to draw price");
  }
  if (els.tradingBacktestRsiChart) {
    renderTradingEmptyChart(els.tradingBacktestRsiChart, "Run backtest to draw RSI");
  }
  if (els.tradingBacktestOperations) {
    els.tradingBacktestOperations.innerHTML = `<div class="empty">No backtest operations</div>`;
  }
  if (els.tradingBacktestOperationCount) els.tradingBacktestOperationCount.textContent = "0";
  if (els.tradingBacktestTrades) {
    els.tradingBacktestTrades.innerHTML = `<div class="empty">No PnL records</div>`;
  }
  if (els.tradingBacktestTradeCount) els.tradingBacktestTradeCount.textContent = "0";
}

function closeTradingPopover(target) {
  if (!target || typeof target.hidePopover !== "function") return;
  if (target.matches?.(":popover-open")) target.hidePopover();
}

function renderTradingMetrics(instance, metrics, latest) {
  const totalPnl = Number(metrics.total_pnl || 0);
  const realized = Number(metrics.realized_pnl || 0);
  const unrealized = Number(metrics.unrealized_pnl || 0);
  const openReturn = Number(metrics.open_return_pct || 0);
  const tradeSize = Number(instance.notional_per_leg || 0);
  const equity = tradeSize + totalPnl;
  const rsiValue = tradingRsiValue(latest);
  const rsiLabel = latest.rsi_label || "OpenD RSI1";
  const rsiHelp = latest.rsi_source || latest.rsi_error || latest.error || "Unavailable";
  const values = [
    ["Equity", dollarText(equity), "trade size + PnL", pnlDirection(totalPnl)],
    ["Total PnL", moneyText(totalPnl), `${moneyText(realized)} realized`, pnlDirection(totalPnl)],
    ["Open PnL", moneyText(unrealized), pctText(openReturn), pnlDirection(unrealized)],
    ["Closed Trades", String(Number(metrics.trade_count || 0)), `Win ${pctText(metrics.win_rate || 0)}`, ""],
    [rsiLabel, Number.isFinite(rsiValue) ? rsiValue.toFixed(2) : "-", latest.time ? `${shortTimeOnly(latest.time)} · ${rsiHelp}` : rsiHelp, ""],
    ["Trade Size", dollarText(tradeSize), "per entry", ""],
  ];
  els.tradingMetricGrid.innerHTML = values
    .map(
      ([label, value, help, direction]) => `
        <div class="trading-metric" data-pnl="${escapeAttribute(direction || "")}">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(help || "")}</small>
        </div>
      `
    )
    .join("");
}

function renderTradingStrategyState(strategyState) {
  const state = strategyState || {};
  const severity = state.severity || "idle";
  const rsiLabel = state.rsi_label || "OpenD RSI1";
  const rsiValue = tradingRsiValue(state);
  const profitTakeEnabled = state.profit_take_enabled !== false;
  const details = [
    [rsiLabel, Number.isFinite(rsiValue) ? rsiValue.toFixed(2) : "-"],
    ["Entry", `<= ${numberText(state.buy_threshold)}`],
    ["Bear Entry", `>= ${numberText(state.sell_threshold)}`],
    ["Take Profit", profitTakeEnabled ? `>= ${pctThresholdText(state.profit_take_pct)}` : "Off"],
  ];
  els.tradingStrategyState.innerHTML = `
    <div class="trading-state-card" data-severity="${escapeAttribute(severity)}">
      <div>
        <span>Strategy State</span>
        <strong>${escapeHtml(state.headline || "Waiting for strategy state")}</strong>
        <small>${escapeHtml(state.detail || "Start the simulation to evaluate the next RSI node.")}</small>
      </div>
      <div class="trading-state-meta">
        ${details
          .map(
            ([label, value]) => `
              <span><b>${escapeHtml(label)}</b> ${escapeHtml(value)}</span>
            `
          )
          .join("")}
      </div>
      <p>${escapeHtml(state.next_action || "No action queued.")}</p>
    </div>
  `;
}

function renderTradingQuotes(instance, latest) {
  const positions = instance.positions || {};
  const quotes = [
    {
      role: "Signal",
      ticker: instance.signal_ticker,
      last: latest.signal_price,
      bid: latest.signal_bid,
      ask: latest.signal_ask,
      help: "RSI source",
      position: null,
    },
    {
      role: "Long",
      ticker: instance.long_ticker,
      last: latest.long_price,
      bid: latest.long_bid,
      ask: latest.long_ask,
      help: "Buy ask / sell bid",
      position: positions.long,
      markPrice: positions.long ? positions.long.mark_price : latest.long_bid,
      markLabel: "Bid mark",
    },
    {
      role: "Bear",
      ticker: instance.short_ticker,
      last: latest.short_price,
      bid: latest.short_bid,
      ask: latest.short_ask,
      help: "Inverse ticker · buy ask / sell bid",
      position: positions.short,
      markPrice: positions.short ? positions.short.mark_price : latest.short_bid,
      markLabel: "Bid mark",
    },
  ];
  els.tradingPositionGrid.hidden = true;
  els.tradingPositionGrid.innerHTML = "";
  els.tradingQuoteStrip.innerHTML = quotes.map(tradingQuoteMarkup).join("");
}

function tradingQuoteMarkup(quote) {
  const position = quote.position;
  const pnl = Number(position?.unrealized_pnl || 0);
  const direction = position ? pnlDirection(pnl) : "";
  const exposureLine = position
    ? `${quote.markLabel || "Mark"} ${priceText(quote.markPrice)} · ${pctText(position.return_pct || 0)} · ${moneyText(pnl)}`
    : quote.role === "Signal"
      ? ""
      : "Flat";
  return `
    <div class="trading-quote-card" data-pnl="${escapeAttribute(direction)}">
      <div>
        <span>${escapeHtml(quote.role)}</span>
        <strong>${escapeHtml(quote.ticker || "-")}</strong>
        <small>${escapeHtml(quote.help)}</small>
      </div>
      <div class="trading-quote-values">
        <b>${escapeHtml(priceText(quote.last))}</b>
        <small>Bid ${escapeHtml(priceText(quote.bid))} · Ask ${escapeHtml(priceText(quote.ask))}</small>
        ${exposureLine ? `<em>${escapeHtml(exposureLine)}</em>` : ""}
      </div>
    </div>
  `;
}

function renderTradingPositions(instance, latest) {
  els.tradingPositionGrid.hidden = true;
  els.tradingPositionGrid.innerHTML = "";
}

function tradingPositionMarkup(label, position, ticker, markPrice, markLabel, flatQuoteText) {
  if (!position) {
    return `
      <div class="trading-position-card">
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(ticker || "-")}</strong>
          <small>Flat · ${escapeHtml(flatQuoteText || `${markLabel} ${priceText(markPrice)}`)}</small>
        </div>
        <b>-</b>
      </div>
    `;
  }
  const pnl = Number(position.unrealized_pnl || 0);
  return `
    <div class="trading-position-card" data-pnl="${escapeAttribute(pnlDirection(pnl))}">
      <div>
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(position.ticker || ticker || "-")} @ ${escapeHtml(priceText(position.entry_price))}</strong>
        <small>${escapeHtml(markLabel)} ${escapeHtml(priceText(markPrice))} · ${escapeHtml(pctText(position.return_pct || 0))}</small>
      </div>
      <b>${escapeHtml(moneyText(pnl))}</b>
    </div>
  `;
}

function quoteSpreadText(bid, ask) {
  return `Bid ${priceText(bid)} · Ask ${priceText(ask)}`;
}

function renderTradingCharts(instance) {
  const points = Array.isArray(instance.price_points) ? instance.price_points : [];
  const latest = instance.latest_market || {};
  const rsiLabel = latest.rsi_label || "OpenD RSI1";
  const rsiValue = tradingRsiValue(latest);
  const rsiStatus = Number.isFinite(rsiValue) ? numberText(rsiValue) : "Unavailable";
  els.tradingPriceMeta.textContent = `${instance.long_ticker}/${instance.short_ticker} · ${latest.time ? shortTimeOnly(latest.time) : "-"}`;
  els.tradingRsiMeta.textContent = `${rsiLabel} ${rsiStatus} · ${latest.rsi_source || latest.rsi_error || latest.source_label || "-"}`;
  renderTradingPriceChart(points, instance, {target: els.tradingPriceChart});
  renderTradingRsiChart(points, {target: els.tradingRsiChart});
}

function renderTradingPriceChart(points, instance, {target, markers = []} = {}) {
  target = target || els.tradingPriceChart;
  const cleanPoints = points.filter(
    (point) => Number.isFinite(Number(point.long_price)) || Number.isFinite(Number(point.short_price))
  );
  if (cleanPoints.length < 2) {
    renderTradingEmptyChart(target, "Waiting for price points");
    return;
  }
  if (renderTradingPriceEchart(cleanPoints, instance, target, markers)) return;
  renderTradingPriceSvgChart(cleanPoints, instance, target, markers);
}

function renderTradingPriceSvgChart(cleanPoints, instance, target, markers = []) {
  disposeTradingChart(target);
  const width = 900;
  const height = 260;
  const padTop = 20;
  const padBottom = 34;
  const padX = 22;
  const values = cleanPoints
    .flatMap((point) => [Number(point.long_price), Number(point.short_price)])
    .filter((value) => Number.isFinite(value));
  const [minValue, maxValue] = paddedDomain(Math.min(...values), Math.max(...values));
  const longLine = tradingLine(cleanPoints, "long_price", minValue, maxValue, width, height, padTop, padBottom, padX);
  const shortLine = tradingLine(cleanPoints, "short_price", minValue, maxValue, width, height, padTop, padBottom, padX);
  const grid = tradingGrid(width, height, padTop, padBottom, padX);
  const markerSvg = tradingPriceMarkers(cleanPoints, markers, minValue, maxValue, width, height, padTop, padBottom, padX);
  target.innerHTML = `
    <svg class="trading-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="Simulated pair prices">
      ${grid}
      <polyline class="trading-price-long" points="${longLine}" />
      <polyline class="trading-price-short" points="${shortLine}" />
      ${markerSvg}
      <text class="trading-axis-label" x="${padX}" y="${height - 10}">${escapeHtml(instance.long_ticker || "Long")}</text>
      <text class="trading-axis-label" x="${width - padX}" y="${height - 10}" text-anchor="end">${escapeHtml(instance.short_ticker || "Short")}</text>
    </svg>
  `;
}

function renderTradingRsiChart(points, {target, markers = []} = {}) {
  target = target || els.tradingRsiChart;
  const cleanPoints = points
    .map((point) => ({...point, _rsiValue: tradingRsiValue(point)}))
    .filter((point) => Number.isFinite(point._rsiValue));
  if (cleanPoints.length < 2) {
    renderTradingEmptyChart(target, "Waiting for RSI points");
    return;
  }
  if (renderTradingRsiEchart(cleanPoints, target, markers)) return;
  renderTradingRsiSvgChart(cleanPoints, target, markers);
}

function renderTradingRsiSvgChart(cleanPoints, target, markers = []) {
  disposeTradingChart(target);
  const width = 720;
  const height = 260;
  const padTop = 20;
  const padBottom = 34;
  const padX = 22;
  const line = tradingLine(cleanPoints, "_rsiValue", 0, 100, width, height, padTop, padBottom, padX);
  const y20 = tradingY(20, 0, 100, height, padTop, padBottom);
  const y80 = tradingY(80, 0, 100, height, padTop, padBottom);
  const markerSvg = tradingRsiMarkers(cleanPoints, markers, width, height, padTop, padBottom, padX);
  target.innerHTML = `
    <svg class="trading-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="RSI line">
      ${tradingGrid(width, height, padTop, padBottom, padX)}
      <line class="trading-rsi-threshold" x1="${padX}" x2="${width - padX}" y1="${y20.toFixed(1)}" y2="${y20.toFixed(1)}" />
      <line class="trading-rsi-threshold" x1="${padX}" x2="${width - padX}" y1="${y80.toFixed(1)}" y2="${y80.toFixed(1)}" />
      <polyline class="trading-rsi-line" points="${line}" />
      ${markerSvg}
      <text class="trading-axis-label" x="${padX}" y="${y20 - 4}">20</text>
      <text class="trading-axis-label" x="${padX}" y="${y80 - 4}">80</text>
    </svg>
  `;
}

function renderTradingPriceEchart(cleanPoints, instance, target, markers = []) {
  const chart = getTradingEchart(target);
  if (!chart) return false;
  const longValues = cleanPoints.map((point) => Number(point.long_price)).filter((value) => Number.isFinite(value));
  const shortValues = cleanPoints.map((point) => Number(point.short_price)).filter((value) => Number.isFinite(value));
  const fallbackValues = longValues.concat(shortValues);
  const longDomain = tradingValueDomain(longValues, fallbackValues);
  const shortDomain = tradingValueDomain(shortValues, fallbackValues);
  const markersByIndex = tradingMarkersByIndex(cleanPoints, markers);
  const longName = instance.long_ticker || "Long";
  const shortName = instance.short_ticker || "Bear";
  const option = {
    backgroundColor: "transparent",
    animationDuration: 240,
    textStyle: tradingEchartTextStyle(),
    grid: {left: 48, right: 52, top: 24, bottom: 30, containLabel: false},
    tooltip: tradingEchartTooltip(cleanPoints, markersByIndex),
    xAxis: tradingEchartXAxis(cleanPoints),
    yAxis: [
      tradingEchartPriceYAxis("left", longDomain, longName, TRADING_CHART_COLORS.long, true),
      tradingEchartPriceYAxis("right", shortDomain, shortName, TRADING_CHART_COLORS.short, false),
    ],
    series: [
      {
        name: longName,
        type: "line",
        yAxisIndex: 0,
        data: tradingEchartSeriesData(cleanPoints, "long_price"),
        smooth: 0.2,
        showSymbol: false,
        connectNulls: true,
        lineStyle: {width: 2.4, color: TRADING_CHART_COLORS.long},
        itemStyle: {color: TRADING_CHART_COLORS.long},
        areaStyle: {color: "rgba(125, 184, 255, 0.06)"},
        endLabel: tradingEchartEndLabel(longName, TRADING_CHART_COLORS.long),
        markPoint: tradingEchartMarkPoint(tradingEchartPriceMarkers(cleanPoints, markers, "long")),
      },
      {
        name: shortName,
        type: "line",
        yAxisIndex: 1,
        data: tradingEchartSeriesData(cleanPoints, "short_price"),
        smooth: 0.2,
        showSymbol: false,
        connectNulls: true,
        lineStyle: {width: 2.2, color: TRADING_CHART_COLORS.short},
        itemStyle: {color: TRADING_CHART_COLORS.short},
        areaStyle: {color: "rgba(245, 189, 79, 0.05)"},
        endLabel: tradingEchartEndLabel(shortName, TRADING_CHART_COLORS.short),
        markPoint: tradingEchartMarkPoint(tradingEchartPriceMarkers(cleanPoints, markers, "short")),
      },
    ],
  };
  target.setAttribute("aria-label", "Simulated pair prices");
  chart.setOption(option, true);
  scheduleTradingChartResize();
  return true;
}

function renderTradingRsiEchart(cleanPoints, target, markers = []) {
  const chart = getTradingEchart(target);
  if (!chart) return false;
  const markersByIndex = tradingMarkersByIndex(cleanPoints, markers);
  const option = {
    backgroundColor: "transparent",
    animationDuration: 240,
    textStyle: tradingEchartTextStyle(),
    grid: {left: 38, right: 20, top: 24, bottom: 30, containLabel: false},
    tooltip: tradingEchartTooltip(cleanPoints, markersByIndex),
    xAxis: tradingEchartXAxis(cleanPoints),
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: {color: TRADING_CHART_COLORS.muted, fontSize: 10, formatter: (value) => Number(value).toFixed(0)},
      axisLine: {lineStyle: {color: TRADING_CHART_COLORS.axis}},
      axisTick: {show: false},
      splitLine: {lineStyle: {color: TRADING_CHART_COLORS.grid}},
    },
    series: [
      {
        name: "RSI",
        type: "line",
        data: tradingEchartSeriesData(cleanPoints, "_rsiValue"),
        smooth: 0.18,
        showSymbol: false,
        connectNulls: true,
        lineStyle: {width: 2.35, color: TRADING_CHART_COLORS.rsi},
        itemStyle: {color: TRADING_CHART_COLORS.rsi},
        areaStyle: {color: "rgba(79, 209, 197, 0.06)"},
        markLine: {
          silent: true,
          symbol: "none",
          label: {
            color: TRADING_CHART_COLORS.muted,
            fontSize: 10,
            formatter: "{b}",
            position: "insideEndTop",
          },
          lineStyle: {
            color: "rgba(245, 189, 79, 0.46)",
            type: "dashed",
            width: 1,
          },
          data: [
            {name: "80", yAxis: 80},
            {name: "20", yAxis: 20},
          ],
        },
        markPoint: tradingEchartMarkPoint(tradingEchartRsiMarkers(cleanPoints, markers)),
      },
    ],
  };
  target.setAttribute("aria-label", "RSI line");
  chart.setOption(option, true);
  scheduleTradingChartResize();
  return true;
}

function renderTradingEmptyChart(target, message) {
  disposeTradingChart(target);
  target.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
}

function getTradingEchart(target) {
  if (!target || !window.echarts || typeof window.echarts.init !== "function") return null;
  if (target.offsetParent === null || target.clientWidth < 40 || target.clientHeight < 40) return null;
  let chart = tradingChartStore.get(target);
  if (!chart || (typeof chart.isDisposed === "function" && chart.isDisposed())) {
    target.innerHTML = "";
    target.classList.add("trading-echart-host");
    chart = window.echarts.init(target, null, {renderer: "canvas"});
    tradingChartStore.set(target, chart);
  }
  return chart;
}

function disposeTradingChart(target) {
  const chart = tradingChartStore.get(target);
  if (chart && typeof chart.dispose === "function" && (!chart.isDisposed || !chart.isDisposed())) {
    chart.dispose();
  }
  tradingChartStore.delete(target);
  if (target) target.classList.remove("trading-echart-host");
}

function scheduleTradingChartResize() {
  window.requestAnimationFrame(() => {
    tradingChartStore.forEach((chart, target) => {
      if (!target.isConnected || (typeof chart.isDisposed === "function" && chart.isDisposed())) {
        tradingChartStore.delete(target);
        return;
      }
      chart.resize();
    });
  });
}

function tradingEchartTextStyle() {
  return {
    color: TRADING_CHART_COLORS.text,
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    fontSize: 11,
  };
}

function tradingEchartXAxis(points) {
  return {
    type: "value",
    min: 0,
    max: Math.max(points.length - 1, 1),
    boundaryGap: false,
    axisLabel: {
      color: TRADING_CHART_COLORS.muted,
      fontSize: 10,
      hideOverlap: true,
      formatter: (value) => tradingAxisTimeLabel(points, value),
    },
    axisLine: {lineStyle: {color: TRADING_CHART_COLORS.axis}},
    axisTick: {show: false},
    splitLine: {show: false},
  };
}

function tradingEchartPriceYAxis(position, domain, name, color, showSplitLine) {
  return {
    type: "value",
    position,
    min: domain[0],
    max: domain[1],
    name,
    nameTextStyle: {color, fontSize: 10, fontWeight: 800, padding: position === "left" ? [0, 0, 0, 4] : [0, 4, 0, 0]},
    axisLabel: {color: TRADING_CHART_COLORS.muted, fontSize: 10, formatter: (value) => `$${priceBareText(value)}`},
    axisLine: {lineStyle: {color: TRADING_CHART_COLORS.axis}},
    axisTick: {show: false},
    splitLine: showSplitLine ? {lineStyle: {color: TRADING_CHART_COLORS.grid}} : {show: false},
  };
}

function tradingEchartSeriesData(points, key) {
  return points.map((point, index) => {
    const value = Number(point[key]);
    return [index, Number.isFinite(value) ? value : null];
  });
}

function tradingEchartEndLabel(name, color) {
  return {
    show: true,
    formatter: name,
    color,
    fontSize: 10,
    fontWeight: 850,
    distance: 6,
  };
}

function tradingEchartMarkPoint(data) {
  return {
    symbolKeepAspect: true,
    z: 6,
    data,
    emphasis: {
      label: {show: true},
    },
  };
}

function tradingEchartPriceMarkers(points, markers, leg) {
  const indexByTime = tradingPointIndex(points);
  const valueKey = leg === "short" ? "short_price" : "long_price";
  return (markers || [])
    .filter((marker) => tradingMarkerLeg(marker) === leg)
    .map((marker) => {
      const pointIndex = indexByTime.get(String(marker.time || ""));
      if (pointIndex === undefined) return null;
      const point = points[pointIndex];
      const value = Number(marker.price ?? point[valueKey]);
      if (!Number.isFinite(value)) return null;
      return tradingEchartMarkerData(marker, pointIndex, value, `${tradingMarkerLabel(marker)}\n${priceText(value)}`);
    })
    .filter(Boolean);
}

function tradingEchartRsiMarkers(points, markers) {
  const indexByTime = tradingPointIndex(points);
  const grouped = new Map();
  (markers || []).forEach((marker) => {
    const pointIndex = indexByTime.get(String(marker.time || ""));
    if (pointIndex === undefined) return;
    const group = grouped.get(pointIndex) || [];
    group.push(marker);
    grouped.set(pointIndex, group);
  });
  return [...grouped.entries()]
    .map(([pointIndex, group]) => {
      const point = points[pointIndex];
      const primary = group.find((marker) => Number.isFinite(Number(marker.rsi))) || group[0];
      const rsi = Number(primary?.rsi ?? point?._rsiValue);
      if (!Number.isFinite(rsi)) return null;
      const signalLabel = rsi >= 80 ? "BEAR" : rsi <= 20 ? "LONG" : tradingMarkerLabel(primary);
      return tradingEchartMarkerData(primary, pointIndex, rsi, `${signalLabel}\n${numberText(rsi)}`, rsi >= 80 ? "sell" : "buy");
    })
    .filter(Boolean);
}

function tradingEchartMarkerData(marker, pointIndex, value, label, forcedType = "") {
  const type = forcedType || tradingMarkerType(marker);
  const isSell = type === "sell";
  const color = isSell ? TRADING_CHART_COLORS.sell : TRADING_CHART_COLORS.buy;
  return {
    name: label.replace(/\n/g, " "),
    coord: [pointIndex, value],
    value,
    symbol: "triangle",
    symbolSize: 12,
    symbolRotate: isSell ? 180 : 0,
    itemStyle: {
      color,
      borderColor: TRADING_CHART_COLORS.bg,
      borderWidth: 2,
    },
    label: {
      show: true,
      formatter: label,
      position: isSell ? "top" : "bottom",
      distance: 8,
      color: "#eff6ff",
      backgroundColor: isSell ? "rgba(112, 35, 50, 0.9)" : "rgba(22, 87, 55, 0.9)",
      borderColor: isSell ? "rgba(255, 107, 122, 0.62)" : "rgba(82, 210, 115, 0.62)",
      borderWidth: 1,
      borderRadius: 4,
      padding: [3, 5],
      fontSize: 10,
      fontWeight: 850,
      lineHeight: 13,
    },
  };
}

function tradingEchartTooltip(points, markersByIndex) {
  return {
    trigger: "axis",
    confine: true,
    appendToBody: true,
    backgroundColor: "rgba(13, 19, 26, 0.96)",
    borderColor: "rgba(154, 168, 182, 0.24)",
    borderWidth: 1,
    textStyle: tradingEchartTextStyle(),
    axisPointer: {
      type: "line",
      lineStyle: {color: "rgba(219, 229, 238, 0.22)", width: 1},
    },
    formatter: (params) => {
      const items = Array.isArray(params) ? params : [params];
      const first = items.find((item) => Array.isArray(item.value));
      const pointIndex = Math.round(Number(first?.value?.[0]));
      const point = points[pointIndex] || {};
      const lines = [`<strong>${escapeHtml(shortDateTime(point.time) || `Point ${pointIndex + 1}`)}</strong>`];
      items
        .filter((item) => item.seriesType === "line" && Array.isArray(item.value))
        .forEach((item) => {
          const value = Number(item.value[1]);
          if (!Number.isFinite(value)) return;
          const marker = `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${escapeAttribute(item.color)};margin-right:6px;"></span>`;
          const suffix = item.seriesName === "RSI" ? numberText(value) : priceText(value);
          lines.push(`${marker}${escapeHtml(item.seriesName)} ${escapeHtml(suffix)}`);
        });
      const rsi = tradingRsiValue(point);
      if (Number.isFinite(rsi) && !items.some((item) => item.seriesName === "RSI")) {
        lines.push(`RSI ${escapeHtml(numberText(rsi))}`);
      }
      const markerLines = markersByIndex.get(pointIndex) || [];
      markerLines.forEach((marker) => lines.push(`<span class="chart-tip-action">${escapeHtml(tradingMarkerTooltipText(marker))}</span>`));
      return lines.join("<br/>");
    },
  };
}

function tradingMarkersByIndex(points, markers) {
  const indexByTime = tradingPointIndex(points);
  const result = new Map();
  (markers || []).forEach((marker) => {
    const pointIndex = indexByTime.get(String(marker.time || ""));
    if (pointIndex === undefined) return;
    const rows = result.get(pointIndex) || [];
    rows.push(marker);
    result.set(pointIndex, rows);
  });
  return result;
}

function tradingMarkerTooltipText(marker) {
  const ticker = marker.ticker ? ` ${marker.ticker}` : "";
  const price = Number.isFinite(Number(marker.price)) ? ` ${priceText(marker.price)}` : "";
  const quote = marker.quote_side ? ` ${String(marker.quote_side).toUpperCase()}` : "";
  const rsi = Number.isFinite(Number(marker.rsi)) ? ` · RSI ${numberText(marker.rsi)}` : "";
  return `${tradingMarkerLabel(marker)}${ticker}${price}${quote}${rsi}`;
}

function tradingAxisTimeLabel(points, value) {
  const index = Math.round(Number(value));
  if (!Number.isFinite(index) || index < 0 || index >= points.length) return "";
  const point = points[index];
  if (!point) return "";
  if (index === 0 || index === points.length - 1) return shortDateTime(point.time);
  return shortTimeOnly(point.time);
}

function tradingValueDomain(values, fallbackValues = []) {
  const source = values.length ? values : fallbackValues;
  if (!source.length) return [0, 1];
  return paddedDomain(Math.min(...source), Math.max(...source));
}

function tradingRsiValue(point) {
  if (!point) return NaN;
  for (const key of ["rsi", "rsi1", "rsi3"]) {
    const raw = point[key];
    if (raw === null || raw === undefined || raw === "") continue;
    const value = Number(raw);
    if (Number.isFinite(value)) return value;
  }
  return NaN;
}

function tradingLine(points, key, minValue, maxValue, width, height, padTop, padBottom, padX) {
  const lastIndex = Math.max(points.length - 1, 1);
  const plotWidth = width - padX * 2;
  return points
    .map((point, index) => {
      const value = Number(point[key]);
      if (!Number.isFinite(value)) return "";
      const x = padX + (index / lastIndex) * plotWidth;
      const y = tradingY(value, minValue, maxValue, height, padTop, padBottom);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
}

function tradingPriceMarkers(points, markers, minValue, maxValue, width, height, padTop, padBottom, padX) {
  const indexByTime = tradingPointIndex(points);
  const lastIndex = Math.max(points.length - 1, 1);
  const plotWidth = width - padX * 2;
  return (markers || [])
    .map((marker) => {
      const pointIndex = indexByTime.get(String(marker.time || ""));
      if (pointIndex === undefined) return "";
      const point = points[pointIndex];
      const leg = String(marker.leg || "").toLowerCase();
      const key = leg === "short" ? "short_price" : "long_price";
      const value = Number(marker.price ?? point[key]);
      if (!Number.isFinite(value)) return "";
      const x = padX + (pointIndex / lastIndex) * plotWidth;
      const y = tradingY(value, minValue, maxValue, height, padTop, padBottom);
      return tradingMarkerSvg(marker, x, y);
    })
    .filter(Boolean)
    .join("");
}

function tradingRsiMarkers(points, markers, width, height, padTop, padBottom, padX) {
  const indexByTime = tradingPointIndex(points);
  const lastIndex = Math.max(points.length - 1, 1);
  const plotWidth = width - padX * 2;
  return (markers || [])
    .map((marker) => {
      const pointIndex = indexByTime.get(String(marker.time || ""));
      if (pointIndex === undefined) return "";
      const point = points[pointIndex];
      const rsi = Number(marker.rsi ?? point._rsiValue);
      if (!Number.isFinite(rsi)) return "";
      const x = padX + (pointIndex / lastIndex) * plotWidth;
      const y = tradingY(rsi, 0, 100, height, padTop, padBottom);
      return tradingMarkerSvg(marker, x, y);
    })
    .filter(Boolean)
    .join("");
}

function tradingMarkerLeg(marker) {
  const leg = String(marker?.leg || "").toLowerCase();
  if (leg === "bear") return "short";
  if (leg === "short" || leg === "long") return leg;
  return "";
}

function tradingMarkerType(marker) {
  return String(marker?.type || "").toLowerCase() === "sell" ? "sell" : "buy";
}

function tradingMarkerLabel(marker) {
  return tradingMarkerType(marker) === "sell" ? "SELL" : "BUY";
}

function tradingMarkerSvg(marker, x, y) {
  const type = tradingMarkerType(marker);
  const label = tradingMarkerLabel(marker);
  const value = Number(marker.price);
  const priceLabel = Number.isFinite(value) ? priceText(value) : "";
  const labelY = type === "sell" ? y - 18 : y + 18;
  const anchorY = type === "sell" ? y - 5 : y + 5;
  return `
    <g class="trading-marker" data-type="${escapeAttribute(type)}">
      <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5.5" />
      <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y.toFixed(1)}" y2="${anchorY.toFixed(1)}" />
      <text x="${x.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle">
        <tspan x="${x.toFixed(1)}">${label}</tspan>
        ${priceLabel ? `<tspan x="${x.toFixed(1)}" dy="11">${escapeHtml(priceLabel)}</tspan>` : ""}
      </text>
    </g>
  `;
}

function tradingPointIndex(points) {
  const index = new Map();
  points.forEach((point, pointIndex) => {
    index.set(String(point.time || ""), pointIndex);
  });
  return index;
}

function tradingY(value, minValue, maxValue, height, padTop, padBottom) {
  const plotHeight = height - padTop - padBottom;
  const span = maxValue - minValue || 1;
  return padTop + (1 - (value - minValue) / span) * plotHeight;
}

function tradingGrid(width, height, padTop, padBottom, padX) {
  const plotBottom = height - padBottom;
  return [0.25, 0.5, 0.75]
    .map((ratio) => {
      const y = padTop + ratio * (plotBottom - padTop);
      return `<line class="trading-grid-line" x1="${padX}" x2="${width - padX}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" />`;
    })
    .join("");
}

function renderTradingEventLog(events) {
  renderTradingEventRows(events, els.tradingEventLog, els.tradingEventCount, "暂无交易操作", 30);
}

function renderTradingEventRows(events, target, countTarget, emptyText, limit = 30) {
  const compacted = compactTradingEvents(events);
  const rows = compacted.slice(-limit).reverse();
  countTarget.textContent = String(compacted.length);
  if (!rows.length) {
    target.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  target.innerHTML = rows
    .map((event) => {
      const display = event._display || tradingEventDisplay(event);
      const countLabel = Number(event._count || 0) > 1 ? ` ×${Number(event._count)}` : "";
      return `
        <div class="trading-event-row" data-severity="${escapeAttribute(event.severity || "info")}">
          <div class="trading-event-main">
            <strong>${escapeHtml(display.title)}${escapeHtml(countLabel)}</strong>
            <span>${escapeHtml(display.detail)}</span>
          </div>
          <small>${escapeHtml(shortTimeOnly(event.time))} · ${escapeHtml(display.typeLabel)}</small>
        </div>
      `;
    })
    .join("");
}

function compactTradingEvents(events) {
  const operationTypes = new Set(["started", "stopped", "signal", "open", "close", "data_warning", "error"]);
  const rows = [];
  for (const event of events || []) {
    if (!operationTypes.has(event.type) || isInternalTradingNoise(event)) continue;
    const display = tradingEventDisplay(event);
    const key = `${event.type || ""}|${event.severity || ""}|${display.title}|${display.detail}`;
    const previous = rows[rows.length - 1];
    if (previous && previous._compactKey === key) {
      previous._count = Number(previous._count || 1) + 1;
      previous.time = event.time || previous.time;
      continue;
    }
    rows.push({...event, _compactKey: key, _display: display, _count: 1});
  }
  return rows;
}

function tradingEventDisplay(event) {
  const type = String(event.type || "event").toLowerCase();
  const ticker = event.ticker || "";
  const price = Number(event.price);
  const quoteSide = String(event.quote_side || "").toUpperCase();
  const quoteText = quoteSide ? `${quoteSide} 价` : "成交价";
  const typeLabels = {
    started: "启动",
    stopped: "停止",
    signal: "信号",
    open: "开仓",
    close: "平仓",
    data_warning: "数据",
    error: "错误",
  };
  if (type === "started") {
    return {title: "模拟已启动", detail: "开始轮询行情与 OpenD RSI。", typeLabel: typeLabels.started};
  }
  if (type === "stopped") {
    return {title: "模拟已停止", detail: "已暂停轮询，不会产生新的交易动作。", typeLabel: typeLabels.stopped};
  }
  if (type === "open") {
    return {
      title: `${tradingEventLegText(event.leg)}开仓${ticker ? ` · ${ticker}` : ""}`,
      detail: `${quoteText} ${Number.isFinite(price) ? priceText(price) : "-"}，数量 ${tradingQtyText(event.qty)}。${tradingReasonText(event.reason)}`,
      typeLabel: typeLabels.open,
    };
  }
  if (type === "close") {
    return {
      title: `${tradingEventLegText(event.leg)}平仓${ticker ? ` · ${ticker}` : ""}`,
      detail: `${quoteText} ${Number.isFinite(price) ? priceText(price) : "-"}，盈亏 ${moneyText(event.pnl)}，回报 ${pctText(event.return_pct)}。${tradingReasonText(event.reason)}`,
      typeLabel: typeLabels.close,
    };
  }
  if (type === "signal") {
    return {title: "策略信号", detail: tradingEventMessageText(event.message), typeLabel: typeLabels.signal};
  }
  if (type === "data_warning") {
    return {title: "数据等待", detail: tradingEventMessageText(event.message), typeLabel: typeLabels.data_warning};
  }
  if (type === "error") {
    return {title: "运行错误", detail: tradingEventMessageText(event.message), typeLabel: typeLabels.error};
  }
  return {title: typeLabels[type] || "运行记录", detail: tradingEventMessageText(event.message || type), typeLabel: typeLabels[type] || "事件"};
}

function tradingEventMessageText(message) {
  const text = String(message || "").trim();
  const lower = text.toLowerCase();
  if (!text) return "暂无详情。";
  if (lower.includes("maximum 10 times per 30 seconds")) {
    return "请求过快：Futu 限制 30 秒内最多 10 次，下一轮会继续尝试。";
  }
  if (lower.includes("opend stockscreen rsi did not return") && lower.includes("watchlist")) {
    const ticker = text.match(/return\s+([A-Z0-9._-]+)/)?.[1];
    return `${ticker || "该标的"} 未从 Futu 自选列表返回 RSI，已改用全市场扫描。`;
  }
  if (lower.includes("opend stockscreen rsi did not return")) {
    const ticker = text.match(/return\s+([A-Z0-9._-]+)/)?.[1];
    return `${ticker || "该标的"} 暂未在 OpenD StockScreen 结果中返回 RSI。`;
  }
  if (lower.includes("futu opend connection unavailable") || lower.includes("network interruption") || lower.includes("disconn")) {
    return "Futu OpenD 连接暂不可用，系统会在下一轮继续尝试。";
  }
  if (lower.includes("packeterr.timeout")) {
    return "Futu OpenD 请求超时，系统会在下一轮继续尝试。";
  }
  if (lower.includes("rotated to long")) {
    return text.replace(": rotated to long", "：切换到多头仓位");
  }
  if (lower.includes("rotated to bear")) {
    return text.replace(": rotated to bear", "：切换到反向仓位");
  }
  if (lower.startsWith("profit take")) {
    return text.replace("Profit take", "触发止盈").replace(" >= ", "，达到止盈阈值 ");
  }
  return text.replace(/^Futu fallback:\\s*/i, "Futu 备用数据：");
}

function tradingEventLegText(leg) {
  return String(leg || "").toLowerCase() === "short" ? "反向" : "多头";
}

function tradingReasonText(reason) {
  const clean = String(reason || "").toLowerCase();
  if (clean === "rsi_extreme_oversold") return "RSI 进入超卖区。";
  if (clean === "rsi_extreme_overbought") return "RSI 进入超买区。";
  if (clean === "rsi_extreme_profit_take") return "达到止盈条件。";
  return clean ? clean.replaceAll("_", " ") : "";
}

function tradingQtyText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (number >= 100) return number.toFixed(1);
  return number.toFixed(3);
}

function isInternalTradingNoise(event) {
  const message = String(event.message || "");
  const legacyBorrowedShortModel =
    message.includes("SELL_SHORT") ||
    message.includes("BUY_TO_COVER") ||
    message.includes("opened pair") ||
    message.includes("closed pair");
  return (event.type === "error" && message.includes("trading_simulator.tmp")) || legacyBorrowedShortModel;
}

function renderTradingTradeLog(trades) {
  renderTradingTradeRows(trades, els.tradingTradeLog, els.tradingTradeCount);
}

function renderTradingTradeRows(trades, target, countTarget, emptyText = "No PnL records", limit = 80) {
  const safeTrades = Array.isArray(trades) ? trades : [];
  const rows = safeTrades.slice(-limit).reverse();
  countTarget.textContent = String(safeTrades.length);
  if (!rows.length) {
    target.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  target.innerHTML = rows
    .map((trade) => {
      const pnl = Number(trade.pnl || 0);
      const path = tradeExecutionPathText(trade);
      return `
        <div class="trading-trade-row" data-pnl="${escapeAttribute(pnlDirection(pnl))}">
          <div>
            <strong>${escapeHtml(tradingLegLabel(trade.leg))} ${escapeHtml(trade.ticker || "-")}</strong>
            <span>${escapeHtml(path)} · ${escapeHtml(pctText(trade.return_pct || 0))}</span>
          </div>
          <b>${escapeHtml(moneyText(pnl))}</b>
        </div>
      `;
    })
    .join("");
}

function tradeExecutionPathText(trade) {
  const entrySide = String(trade.entry_quote_side || "").toUpperCase();
  const exitSide = String(trade.exit_quote_side || "").toUpperCase();
  const entry = `${priceText(trade.entry_price)}${entrySide ? ` ${entrySide}` : ""}`;
  const exit = `${priceText(trade.exit_price)}${exitSide ? ` ${exitSide}` : ""}`;
  if (String(trade.leg || "").toLowerCase() === "short") {
    return `Buy Bear ${entry} -> Sell Bear ${exit}`;
  }
  return `Buy Long ${entry} -> Sell Long ${exit}`;
}

function tradingLegLabel(leg) {
  return String(leg || "").toLowerCase() === "short" ? "BEAR" : "LONG";
}

async function createTradingInstance() {
  const longTicker = cleanTickerInput(els.tradingLongTickerInput.value);
  const shortTicker = cleanTickerInput(els.tradingShortTickerInput.value);
  const signalTicker = cleanTickerInput(els.tradingSignalTickerInput.value || longTicker);
  if (!longTicker || !shortTicker) {
    alert("Long and Bear tickers are required.");
    return;
  }
  els.createTradingInstanceButton.disabled = true;
  try {
    const data = await api("/api/trading/simulate/instances", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        name: els.tradingNameInput.value.trim(),
        pair_id: els.tradingPairSelect.value || "custom",
        signal_ticker: signalTicker,
        long_ticker: longTicker,
        short_ticker: shortTicker,
        notional_per_leg: Number(els.tradingNotionalInput.value || 1000),
        poll_seconds: Number(els.tradingPollSecondsInput.value || 5),
      }),
    });
    activeTradingInstanceId = data.instance?.id || activeTradingInstanceId;
    els.tradingNameInput.value = "";
    await refreshTradingInstances();
  } catch (error) {
    alert(error.message);
  } finally {
    els.createTradingInstanceButton.disabled = false;
  }
}

async function startTradingInstance() {
  if (!activeTradingInstanceId) return;
  els.startTradingInstanceButton.disabled = true;
  try {
    await api(`/api/trading/simulate/instances/${encodeURIComponent(activeTradingInstanceId)}/start`, {method: "POST"});
    await refreshTradingInstances();
  } catch (error) {
    alert(error.message);
  }
}

async function stopTradingInstance() {
  if (!activeTradingInstanceId) return;
  els.stopTradingInstanceButton.disabled = true;
  try {
    await api(`/api/trading/simulate/instances/${encodeURIComponent(activeTradingInstanceId)}/stop`, {method: "POST"});
    await refreshTradingInstances();
  } catch (error) {
    alert(error.message);
  }
}

async function deleteTradingInstance() {
  if (!activeTradingInstanceId) return;
  if (!window.confirm("Delete this simulation instance?")) return;
  const deletedId = activeTradingInstanceId;
  els.deleteTradingInstanceButton.disabled = true;
  try {
    await api(`/api/trading/simulate/instances/${encodeURIComponent(deletedId)}`, {method: "DELETE"});
    activeTradingInstanceId = null;
    await refreshTradingInstances();
  } catch (error) {
    alert(error.message);
  }
}

async function runTradingBacktest() {
  if (!activeTradingInstanceId) return;
  const start = els.tradingBacktestStart.value;
  const end = els.tradingBacktestEnd.value;
  if (!start || !end) {
    renderTradingBacktestEmpty("Start and end are required");
    return;
  }
  const requestId = ++tradingBacktestRequest;
  els.runTradingBacktestButton.disabled = true;
  els.runTradingBacktestButton.textContent = "Running";
  renderTradingBacktestEmpty("Running daily backtests");
  try {
    const data = await api(`/api/trading/simulate/instances/${encodeURIComponent(activeTradingInstanceId)}/backtest`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        start,
        end,
        strategy_id: els.tradingDetailStrategySelect.value || latestTradingDetail?.strategy_id || "rsi_extreme",
        profit_take_percent: Number(els.tradingDetailProfitTakeInput.value || 4),
      }),
    });
    if (requestId !== tradingBacktestRequest) return;
    tradingBacktestResult = data.backtest || null;
    renderTradingBacktestResult(tradingBacktestResult);
    await loadTradingInstanceDetail(activeTradingInstanceId);
  } catch (error) {
    if (requestId !== tradingBacktestRequest) return;
    tradingBacktestResult = null;
    renderTradingBacktestEmpty(error.message);
  } finally {
    if (requestId === tradingBacktestRequest) {
      els.runTradingBacktestButton.disabled = false;
      els.runTradingBacktestButton.textContent = "Run Backtest";
    }
  }
}

function renderTradingBacktestResult(result) {
  if (!result) {
    renderTradingBacktestEmpty();
    return;
  }
  const dailyResults = tradingBacktestDailyResults(result);
  if (!dailyResults.length) {
    renderTradingBacktestEmpty("No daily backtest results");
    return;
  }
  const selectedExists = dailyResults.some((item) => tradingBacktestDayKey(item) === tradingBacktestSelectedDate);
  if (!selectedExists) {
    tradingBacktestSelectedDate = tradingBacktestDayKey(dailyResults[dailyResults.length - 1]);
  }
  renderTradingBacktestPeriodSummary(result, dailyResults);
  renderTradingBacktestDailyList(dailyResults);
  const selected = dailyResults.find((item) => tradingBacktestDayKey(item) === tradingBacktestSelectedDate) || dailyResults[0];
  renderTradingBacktestDayDetail(selected);
}

function tradingBacktestDailyResults(result) {
  const rows = Array.isArray(result?.daily_results) && result.daily_results.length
    ? result.daily_results
    : result
      ? [result]
      : [];
  return rows
    .slice()
    .sort((left, right) => tradingBacktestDayKey(left).localeCompare(tradingBacktestDayKey(right)));
}

function tradingBacktestDayKey(result) {
  return String(result?.date || result?.start || "").slice(0, 10);
}

function renderTradingBacktestPeriodSummary(result, dailyResults) {
  const period = result.period_metrics || {};
  const totalPnl = Number(period.total_pnl ?? result.final_pnl ?? result.metrics?.total_pnl ?? 0);
  const wins = Number(period.winning_days ?? dailyResults.filter((item) => item.outcome === "win").length);
  const losses = Number(period.losing_days ?? dailyResults.filter((item) => item.outcome === "loss").length);
  const flats = Number(period.flat_days ?? dailyResults.filter((item) => item.outcome === "flat").length);
  const decided = wins + losses;
  const winRate = Number(period.win_rate ?? (decided ? wins / decided : 0));
  const averagePnl = Number(period.average_daily_pnl ?? (dailyResults.length ? totalPnl / dailyResults.length : 0));
  const bestDay = period.best_day || dailyResults.reduce(
    (best, item) => !best || Number(item.final_pnl || 0) > Number(best.final_pnl || 0) ? item : best,
    null
  );
  const worstDay = period.worst_day || dailyResults.reduce(
    (worst, item) => !worst || Number(item.final_pnl || 0) < Number(worst.final_pnl || 0) ? item : worst,
    null
  );
  const bestDate = String(bestDay?.date || bestDay?.start || "").slice(5, 10);
  const worstDate = String(worstDay?.date || worstDay?.start || "").slice(5, 10);
  const bestPnl = Number(bestDay?.pnl ?? bestDay?.final_pnl ?? 0);
  const worstPnl = Number(worstDay?.pnl ?? worstDay?.final_pnl ?? 0);
  const noDataCount = Number(period.no_data_day_count ?? result.no_data_dates?.length ?? 0);
  const primaryValues = [
    ["Total PnL", moneyText(totalPnl), `${dailyResults.length} trading days`, pnlDirection(totalPnl)],
    ["Total Win Rate", `${(winRate * 100).toFixed(1)}%`, `${wins} wins / ${losses} losses · flats excluded`, winRate >= 0.5 ? "up" : "down"],
    ["Daily Record", `${wins}-${losses}-${flats}`, "Win · Loss · Flat", ""],
    ["Avg Day", moneyText(averagePnl), noDataCount ? `${noDataCount} weekdays without data` : "All weekdays covered", pnlDirection(averagePnl)],
  ];
  const detailValues = [
    ["Best Day", moneyText(bestPnl), bestDate || "-", pnlDirection(bestPnl)],
    ["Worst Day", moneyText(worstPnl), worstDate || "-", pnlDirection(worstPnl)],
    ["Data Coverage", noDataCount ? `${noDataCount} missing` : "Complete", `${dailyResults.length} trading days`, noDataCount ? "down" : "up"],
    ["Range", backtestRangeText(result), result.source_label || result.source || "-", ""],
  ];
  els.tradingBacktestPeriodSummary.innerHTML = primaryValues
    .map(
      ([label, value, help, direction]) => `
        <div class="trading-metric" data-pnl="${escapeAttribute(direction || "")}">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(help || "")}</small>
        </div>
      `
    )
    .join("");
  if (els.tradingBacktestPeriodDetails) {
    els.tradingBacktestPeriodDetails.innerHTML = detailValues
      .map(
        ([label, value, help, direction]) => `
          <div class="trading-tip-metric" data-pnl="${escapeAttribute(direction || "")}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value || "-")}</strong>
            <small>${escapeHtml(help || "")}</small>
          </div>
        `
      )
      .join("");
  }
  if (els.tradingBacktestMoreButton) els.tradingBacktestMoreButton.hidden = false;
}

function renderTradingBacktestDailyList(dailyResults) {
  els.tradingBacktestDailySection.hidden = false;
  els.tradingBacktestDailyCount.textContent = `${dailyResults.length} ${dailyResults.length === 1 ? "day" : "days"}`;
  els.tradingBacktestDailyList.innerHTML = dailyResults
    .slice()
    .reverse()
    .map((day) => {
      const key = tradingBacktestDayKey(day);
      const pnl = Number(day.final_pnl || day.metrics?.total_pnl || 0);
      const outcome = day.outcome || (pnl > 0 ? "win" : pnl < 0 ? "loss" : "flat");
      const metrics = day.metrics || {};
      return `
        <button
          class="trading-backtest-day-button${key === tradingBacktestSelectedDate ? " active" : ""}"
          type="button"
          data-date="${escapeAttribute(key)}"
          data-outcome="${escapeAttribute(outcome)}"
        >
          <span>${escapeHtml(shortBacktestDate(key))}</span>
          <strong>${escapeHtml(moneyText(pnl))}</strong>
          <small>${escapeHtml(String(outcome).toUpperCase())} · ${Number(metrics.trade_count || 0)} trades</small>
        </button>
      `;
    })
    .join("");
}

function renderTradingBacktestDayDetail(result) {
  if (!result) return;
  els.tradingBacktestDayDetail.hidden = false;
  const dayKey = tradingBacktestDayKey(result);
  const finalPnl = Number(result.final_pnl || result.metrics?.total_pnl || 0);
  const outcome = result.outcome || (finalPnl > 0 ? "win" : finalPnl < 0 ? "loss" : "flat");
  els.tradingBacktestSelectedDate.textContent = dayKey || "-";
  els.tradingBacktestSelectedOutcome.textContent = `${String(outcome).toUpperCase()} · ${moneyText(finalPnl)}`;
  els.tradingBacktestSelectedOutcome.dataset.outcome = outcome;
  const metrics = result.metrics || {};
  const realized = Number(metrics.realized_pnl || 0);
  const openPnl = Number(metrics.unrealized_pnl || 0);
  const trades = Array.isArray(result.trades) ? result.trades : [];
  const operations = Array.isArray(result.operations) ? result.operations : [];
  const primaryValues = [
    ["Final PnL", moneyText(finalPnl), `${moneyText(realized)} realized`, pnlDirection(finalPnl)],
    ["Closed Trades", String(Number(metrics.trade_count || trades.length || 0)), `Win ${pctText(metrics.win_rate || 0)}`, ""],
    ["Open PnL", moneyText(openPnl), pctText(metrics.open_return_pct || 0), pnlDirection(openPnl)],
  ];
  const factValues = [
    ["Points", String(Number(result.point_count || 0)), `RSI ready ${Number(result.rsi_ready_count || 0)}`, ""],
    ["Range", backtestRangeText(result), "Selected session", ""],
    ["Source", result.source_label || result.source || "-", "Historical market data", ""],
  ];
  els.tradingBacktestSummary.innerHTML = primaryValues
    .map(
      ([label, value, help, direction]) => `
        <div class="trading-metric" data-pnl="${escapeAttribute(direction || "")}">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(help || "")}</small>
        </div>
      `
    )
    .join("");
  if (els.tradingBacktestDayFacts) {
    els.tradingBacktestDayFacts.innerHTML = factValues
      .map(
        ([label, value, help, direction]) => `
          <div class="trading-tip-metric" data-pnl="${escapeAttribute(direction || "")}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value || "-")}</strong>
            <small>${escapeHtml(help || "")}</small>
          </div>
        `
      )
      .join("");
  }
  renderTradingBacktestCharts(result);
  renderTradingEventRows(operations, els.tradingBacktestOperations, els.tradingBacktestOperationCount, "No backtest operations");
  renderTradingTradeRows(trades, els.tradingBacktestTrades, els.tradingBacktestTradeCount);
}

function shortBacktestDate(value) {
  const date = parseTradingDate(`${String(value || "").slice(0, 10)}T12:00:00`);
  if (!date) return String(value || "-");
  return new Intl.DateTimeFormat("en-US", {
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  }).format(date);
}

function selectTradingBacktestDay(event) {
  const button = event.target.closest(".trading-backtest-day-button");
  if (!button || !tradingBacktestResult) return;
  const date = button.dataset.date || "";
  const dailyResults = tradingBacktestDailyResults(tradingBacktestResult);
  const selected = dailyResults.find((item) => tradingBacktestDayKey(item) === date);
  if (!selected) return;
  tradingBacktestSelectedDate = date;
  if (els.tradingBacktestAudit) els.tradingBacktestAudit.open = false;
  closeTradingPopover(document.querySelector("#tradingBacktestDayTip"));
  renderTradingBacktestDailyList(dailyResults);
  renderTradingBacktestDayDetail(selected);
  window.setTimeout(scheduleTradingChartResize, 40);
}

function renderTradingBacktestCharts(result) {
  const points = Array.isArray(result?.price_points) ? result.price_points : [];
  const markers = Array.isArray(result?.markers) ? result.markers : [];
  els.tradingBacktestPriceMeta.textContent = `${result.long_ticker || "Long"}/${result.short_ticker || "Bear"} · ${Number(points.length)} points · ${Number(markers.length)} marks`;
  els.tradingBacktestRsiMeta.textContent = `${result.source_label || "Backtest RSI"} · ${Number(result.rsi_ready_count || 0)} ready`;
  renderTradingPriceChart(points, result, {
    target: els.tradingBacktestPriceChart,
    markers,
  });
  renderTradingRsiChart(points, {
    target: els.tradingBacktestRsiChart,
    markers,
  });
}

function backtestRangeText(result) {
  const start = shortDateTime(result?.start);
  const end = shortDateTime(result?.end);
  if (!start || !end) return "-";
  return `${start} -> ${end}`;
}

function strategyName(strategyId) {
  const strategy = tradingStrategies.find((item) => item.id === strategyId);
  return strategy?.label || String(strategyId || "-").replaceAll("_", " ");
}

function tradingStatusText(status) {
  const clean = String(status || "idle").toLowerCase();
  if (clean === "running") return "Running";
  if (clean === "idle") return "Idle";
  if (clean === "failed") return "Failed";
  return clean.toUpperCase();
}

function cleanTickerInput(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9._-]/g, "")
    .split(".")
    .pop();
}

function pnlDirection(value) {
  const number = Number(value || 0);
  if (number > 0) return "up";
  if (number < 0) return "down";
  return "flat";
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
  if (shortTermTracking && shortTermTicker && shortTermTicker !== requestedTicker) {
    await stopShortTermTracking({ticker: shortTermTicker, silent: true});
  }
  if (!shortTermTracking && shortTermTicker !== requestedTicker) {
    resetShortTermPanel();
  }
  const dimension = els.dimensionFilter.value;
  const data = await api(`/api/ticker/${requestedTicker}?dimension=${encodeURIComponent(dimension)}&min_importance=0`);
  if (requestedTicker !== selectedTicker) return;
  els.detailTitle.textContent = requestedTicker;
  els.detailScore.textContent = data.score ? `${Number(data.score.total_score).toFixed(1)} · ${data.score.grade}` : "-";
  if (activeDetailTab === "chart") renderTradingViewChart(requestedTicker);
  if (activeDetailTab === "shortterm") loadShortTermSnapshot();
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
  stopShortTermTracking({silent: true});
  resetShortTermPanel();
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
    ["shortterm", els.shortTermTab, els.shortTermPanel],
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
  if (tab === "shortterm") {
    if (selectedTicker && shortTermTracking) {
      loadShortTermSnapshot();
    } else {
      resetShortTermPanel();
    }
  }
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

async function toggleShortTermTracking() {
  if (shortTermTracking) {
    await stopShortTermTracking();
  } else {
    await startShortTermTracking();
  }
}

async function startShortTermTracking() {
  if (!selectedTicker) return;
  const ticker = selectedTicker.toUpperCase();
  els.shortTermTrackButton.disabled = true;
  els.shortTermStatus.textContent = "Starting";
  try {
    const data = await api(`/api/ticker/${ticker}/short-term/start`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({window: Number(els.shortTermWindow.value || 160)}),
    });
    if (ticker !== selectedTicker) return;
    shortTermTracking = true;
    shortTermTicker = ticker;
    shortTermUnloadSent = false;
    renderShortTerm(data);
    scheduleShortTermPoll();
  } catch (error) {
    shortTermTracking = false;
    shortTermTicker = ticker;
    renderShortTerm({ticker, tracking: false, points: [], error: error.message});
  } finally {
    els.shortTermTrackButton.disabled = !selectedTicker;
  }
}

async function stopShortTermTracking({ticker = null, silent = false} = {}) {
  window.clearTimeout(shortTermTimer);
  shortTermTimer = null;
  const target = String(ticker || shortTermTicker || selectedTicker || "").toUpperCase();
  shortTermTracking = false;
  shortTermTicker = null;
  if (!target) {
    if (!silent) resetShortTermPanel();
    return;
  }
  try {
    const data = await api(`/api/ticker/${target}/short-term/stop`, {method: "POST"});
    if (!silent && (!selectedTicker || target === selectedTicker)) renderShortTerm(data);
  } catch (error) {
    if (!silent) renderShortTerm({ticker: target, tracking: false, points: [], error: error.message});
  }
  if (!silent) resetShortTermPanel();
}

function releaseShortTermTrackingOnPageExit() {
  if (!shortTermTracking || !shortTermTicker || shortTermUnloadSent) return;
  const target = shortTermTicker.toUpperCase();
  shortTermUnloadSent = true;
  window.clearTimeout(shortTermTimer);
  shortTermTimer = null;
  shortTermTracking = false;
  shortTermTicker = null;
  const url = `/api/ticker/${encodeURIComponent(target)}/short-term/stop`;
  if (navigator.sendBeacon) {
    const sent = navigator.sendBeacon(url, new Blob([], {type: "text/plain"}));
    if (sent) return;
  }
  try {
    fetch(url, {method: "POST", keepalive: true}).catch(() => {});
  } catch (error) {
    // Best-effort cleanup during page unload.
  }
}

async function loadShortTermSnapshot() {
  if (!selectedTicker || !shortTermTracking) {
    resetShortTermPanel();
    return;
  }
  const ticker = selectedTicker.toUpperCase();
  try {
    const data = await api(`/api/ticker/${ticker}/short-term?window=${encodeURIComponent(els.shortTermWindow.value || "160")}`);
    if (ticker !== selectedTicker || ticker !== shortTermTicker) return;
    renderShortTerm(data);
  } catch (error) {
    if (ticker !== selectedTicker) return;
    renderShortTerm({ticker, tracking: true, points: [], error: error.message});
  }
}

function scheduleShortTermPoll() {
  window.clearTimeout(shortTermTimer);
  if (!shortTermTracking) return;
  shortTermTimer = window.setTimeout(async () => {
    await loadShortTermSnapshot();
    scheduleShortTermPoll();
  }, SHORT_TERM_POLL_MS);
}

function resetShortTermPanel() {
  window.clearTimeout(shortTermTimer);
  if (!shortTermTracking) shortTermTimer = null;
  els.shortTermTrackButton.disabled = !selectedTicker;
  els.shortTermTrackButton.textContent = "Start Tracking";
  els.shortTermStatus.textContent = selectedTicker ? "Tracking off" : "Select a ticker";
  els.shortTermDecision.innerHTML = "";
  els.shortTermRules.innerHTML = "";
  els.shortTermMetrics.innerHTML = "";
  els.shortTermChart.innerHTML = `<div class="empty">${selectedTicker ? "Tracking off" : "Select a ticker"}</div>`;
  els.shortTermTape.innerHTML = "";
}

function renderShortTerm(data) {
  const ticker = String(data?.ticker || selectedTicker || "").toUpperCase();
  const points = Array.isArray(data?.points) ? data.points : [];
  const indicators = data?.indicators || {};
  shortTermTracking = Boolean(data?.tracking);
  shortTermTicker = shortTermTracking ? ticker : null;
  els.shortTermTrackButton.textContent = shortTermTracking ? "Stop Tracking" : "Start Tracking";
  els.shortTermTrackButton.disabled = !selectedTicker;
  if (data?.error) {
    els.shortTermStatus.textContent = data.error;
  } else if (shortTermTracking) {
    const asOf = data.as_of ? formatShortTime(data.as_of) : "Waiting";
    els.shortTermStatus.textContent = `${data.source_label || "Futu 1m K-line"} · ${asOf}`;
  } else {
    els.shortTermStatus.textContent = "Tracking off";
  }
  renderShortTermDecision(indicators, points, data?.error);
  renderShortTermRules(indicators.signal?.rules || []);
  renderShortTermMetrics(indicators, points);
  renderShortTermChart(points, data?.error);
  renderShortTermTape(points);
}

function renderShortTermDecision(indicators, points, error) {
  if (error) {
    els.shortTermDecision.innerHTML = "";
    return;
  }
  if (!points.length) {
    els.shortTermDecision.innerHTML = "";
    return;
  }
  const signal = indicators.signal || {};
  const bias = String(signal.bias || "neutral");
  const summary = signal.summary || "中性：等待规则共振。";
  const score = Number(signal.bias_score || 0);
  els.shortTermDecision.innerHTML = `
    <div class="shortterm-decision-card" data-bias="${escapeAttribute(bias)}">
      <span>${escapeHtml(biasLabel(bias))}</span>
      <strong>${escapeHtml(summary)}</strong>
      <small>规则分 ${score >= 0 ? "+" : ""}${Number.isFinite(score) ? score : 0}</small>
    </div>
  `;
}

function renderShortTermRules(rules) {
  const safeRules = Array.isArray(rules) ? rules : [];
  if (!safeRules.length) {
    els.shortTermRules.innerHTML = "";
    return;
  }
  els.shortTermRules.innerHTML = safeRules
    .map((rule) => {
      const tip = `${rule.condition || ""} ${rule.conclusion || ""}`.trim();
      return `
        <div class="shortterm-rule has-hover-card" data-status="${escapeAttribute(rule.status || "watch")}" data-tip="${escapeAttribute(tip)}">
          <span>${escapeHtml(rule.label || "-")}</span>
          <strong>${escapeHtml(ruleStatusText(rule.status))}</strong>
        </div>
      `;
    })
    .join("");
}

function renderShortTermMetrics(indicators, points) {
  if (!points.length) {
    els.shortTermMetrics.innerHTML = "";
    return;
  }
  const kdj = indicators.kdj || {};
  const volume = indicators.volume || {};
  const ema = indicators.ema || {};
  const atr = indicators.atr || {};
  const openingRange = indicators.opening_range || {};
  const guide = indicatorGuideByLabel(indicators.indicator_guide);
  const metrics = [
    ["Price", priceText(indicators.price), signalLabel(indicators.signal?.label), "最新 1 分钟 K 线收盘价。"],
    ["VWAP", priceText(indicators.vwap), pctText(indicators.vwap_deviation), hoverText(guide.VWAP)],
    ["EMA9/21", `${priceBareText(ema.ema9)}/${priceBareText(ema.ema21)}`, stateLabel(ema.state), hoverText(guide["EMA9/21"])],
    ["OR15", orText(openingRange), stateLabel(openingRange.state), hoverText(guide.OR15)],
    ["RSI", numberText(indicators.rsi14), rsiLabel(indicators.rsi14), hoverText(guide["RSI/KDJ"])],
    ["KDJ", `${numberText(kdj.k)}/${numberText(kdj.d)}/${numberText(kdj.j)}`, kdjMetricLabel(kdj), hoverText(guide["RSI/KDJ"])],
    ["Volume", volumeRatioText(volume), volumeHelpText(volume), hoverText(guide["Volume z"])],
    ["ATR1m", pctText(atr.atr_pct), stateLabel(atr.state), hoverText(guide.ATR1m)],
    ["5m", pctText(indicators.return_5m), "return", "最近 5 分钟收益率，用 1 分钟收盘价滚动计算。"],
    ["15m", pctText(indicators.return_15m), "return", "最近 15 分钟收益率，用 1 分钟收盘价滚动计算。"],
  ];
  els.shortTermMetrics.innerHTML = metrics
    .map(
      ([label, value, help, tip]) => `
        <div class="shortterm-metric has-hover-card" data-tip="${escapeAttribute(tip || help || "")}">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(help || "")}</small>
        </div>
      `
    )
    .join("");
}

function renderShortTermChart(points, error) {
  const cleanPoints = points.filter((point) => Number.isFinite(Number(point.close)));
  if (error) {
    els.shortTermChart.innerHTML = `<div class="empty">${escapeHtml(error)}</div>`;
    return;
  }
  if (cleanPoints.length < 2) {
    els.shortTermChart.innerHTML = `<div class="empty">${shortTermTracking ? "Waiting for 1m data" : "Tracking off"}</div>`;
    return;
  }
  const width = 820;
  const height = 280;
  const priceTop = 22;
  const priceHeight = 172;
  const volumeTop = 218;
  const volumeHeight = 42;
  const closes = cleanPoints.map((point) => Number(point.close));
  const vwaps = cleanPoints.map((point) => Number(point.vwap)).filter((value) => Number.isFinite(value));
  const volumes = cleanPoints.map((point) => Number(point.volume || 0));
  const priceValues = closes.concat(vwaps);
  const minClose = Math.min(...priceValues);
  const maxClose = Math.max(...priceValues);
  const priceSpan = maxClose - minClose || 1;
  const maxVolume = Math.max(...volumes, 1);
  const lastIndex = cleanPoints.length - 1;
  const line = cleanPoints
    .map((point, index) => {
      const x = (index / lastIndex) * width;
      const y = priceTop + (1 - (Number(point.close) - minClose) / priceSpan) * priceHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const vwapLine = cleanPoints
    .filter((point) => Number.isFinite(Number(point.vwap)))
    .map((point, index) => {
      const sourceIndex = cleanPoints.indexOf(point);
      const x = (sourceIndex / lastIndex) * width;
      const y = priceTop + (1 - (Number(point.vwap) - minClose) / priceSpan) * priceHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const bars = cleanPoints
    .map((point, index) => {
      const x = (index / lastIndex) * width;
      const barHeight = (Number(point.volume || 0) / maxVolume) * volumeHeight;
      return `<rect x="${x.toFixed(1)}" y="${(volumeTop + volumeHeight - barHeight).toFixed(1)}" width="3" height="${barHeight.toFixed(1)}" />`;
    })
    .join("");
  const latest = cleanPoints[cleanPoints.length - 1];
  els.shortTermChart.innerHTML = `
    <svg class="shortterm-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="1 minute price and volume">
      <line class="shortterm-grid-line" x1="0" x2="${width}" y1="${priceTop + priceHeight}" y2="${priceTop + priceHeight}" />
      ${vwapLine ? `<polyline class="shortterm-vwap-line" points="${vwapLine}" />` : ""}
      <polyline class="shortterm-price-line" points="${line}" />
      <g class="shortterm-volume-bars">${bars}</g>
    </svg>
    <div class="shortterm-chart-foot">
      <span>${escapeHtml(cleanPoints[0].time || "")}</span>
      <strong>${escapeHtml(priceText(latest.close))}</strong>
      <span>${escapeHtml(latest.time || "")}</span>
    </div>
  `;
}

function renderShortTermTape(points) {
  const rows = points.slice(-8).reverse();
  if (!rows.length) {
    els.shortTermTape.innerHTML = "";
    return;
  }
  els.shortTermTape.innerHTML = rows
    .map((point) => {
      const index = points.indexOf(point);
      const prev = index > 0 ? Number(points[index - 1].close) : NaN;
      const current = Number(point.close);
      const change = Number.isFinite(prev) && prev ? current / prev - 1 : null;
      return `
        <div class="shortterm-tape-row">
          <span>${escapeHtml(shortTimeOnly(point.time))}</span>
          <strong>${escapeHtml(priceText(point.close))}</strong>
          <span>${escapeHtml(pctText(change))}</span>
          <span>${escapeHtml(volumeText(point.volume))}</span>
        </div>
      `;
    })
    .join("");
}

function signalLabel(value) {
  const label = String(value || "neutral");
  const labels = {
    overbought_volume: "过热放量",
    oversold_reversal_watch: "超跌放量",
    overbought: "超买",
    oversold: "超卖",
    volume_spike: "放量",
    neutral: "中性",
  };
  return labels[label] || label.replaceAll("_", " ");
}

function biasLabel(value) {
  const labels = {
    strong_long_bias: "强多",
    long_bias: "偏多",
    neutral: "中性",
    short_bias: "偏空",
    strong_short_bias: "强空",
  };
  return labels[String(value || "neutral")] || "中性";
}

function ruleStatusText(value) {
  const labels = {
    pass: "满足",
    fail: "不满足",
    watch: "观察",
    warn: "警惕",
    pending: "等待",
  };
  return labels[String(value || "watch")] || "观察";
}

function stateLabel(value) {
  const labels = {
    bullish: "偏多",
    bearish: "偏空",
    mixed: "混杂",
    above: "上方",
    below: "下方",
    inside: "区间内",
    forming: "形成中",
    compressed: "压缩",
    tradable: "可做T",
    wide: "偏大",
    spike: "放量",
    dry: "缩量",
    normal: "正常",
    unknown: "-",
  };
  return labels[String(value || "unknown")] || String(value || "-");
}

function indicatorGuideByLabel(items) {
  const result = {};
  for (const item of Array.isArray(items) ? items : []) {
    result[item.label] = item;
  }
  return result;
}

function hoverText(item) {
  if (!item) return "";
  return `${item.meaning || ""} ${item.condition || ""}`.trim();
}

function kdjMetricLabel(kdj) {
  const k = Number(kdj.k);
  const d = Number(kdj.d);
  const j = Number(kdj.j);
  if (!Number.isFinite(k) || !Number.isFinite(d) || !Number.isFinite(j)) return "-";
  if (k >= 80 && j >= 90) return "过热";
  if (k <= 20 && j <= 10) return "过冷";
  return k > d ? "拐头向上" : "拐头向下";
}

function volumeRatioText(volume) {
  const ratio = Number(volume?.ratio);
  if (!Number.isFinite(ratio)) return "-";
  return `${ratio.toFixed(2)}x`;
}

function volumeHelpText(volume) {
  const state = stateLabel(volume?.state);
  const zscore = Number(volume?.zscore);
  if (!Number.isFinite(zscore)) return state;
  return `${state} · z ${zscore.toFixed(1)}`;
}

function orText(openingRange) {
  const high = Number(openingRange?.high);
  const low = Number(openingRange?.low);
  if (!Number.isFinite(high) || !Number.isFinite(low)) return "-";
  return `${priceBareText(low)}-${priceBareText(high)}`;
}

function priceText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `$${number >= 100 ? number.toFixed(2) : number.toFixed(3)}`;
}

function priceBareText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number >= 100 ? number.toFixed(2) : number.toFixed(3);
}

function moneyText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const prefix = number >= 0 ? "+" : "-";
  return `${prefix}$${Math.abs(number).toFixed(2)}`;
}

function dollarText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `$${Math.abs(number).toFixed(2)}`;
}

function pctText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number >= 0 ? "+" : ""}${(number * 100).toFixed(2)}%`;
}

function pctThresholdText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(2)}%`;
}

function volumeText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (Math.abs(number) >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (Math.abs(number) >= 1_000) return `${(number / 1_000).toFixed(1)}K`;
  return number.toFixed(0);
}

function shortTimeOnly(value) {
  const text = String(value || "");
  if (text.includes(" ")) return text.split(" ").pop().slice(0, 5);
  if (text.includes("T")) return text.split("T").pop().slice(0, 5);
  return text.slice(0, 5);
}

function parseTradingDate(value) {
  if (!value) return null;
  const date = new Date(String(value).replace(" ", "T"));
  return Number.isFinite(date.getTime()) ? date : null;
}

function currentNewYorkDate() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return new Date(`${values.year}-${values.month}-${values.day}T12:00:00`);
}

function regularUsSessionRange(referenceDate) {
  const reference = referenceDate instanceof Date && Number.isFinite(referenceDate.getTime()) ? referenceDate : currentNewYorkDate();
  const start = new Date(reference);
  start.setHours(9, 30, 0, 0);
  const end = new Date(reference);
  end.setHours(16, 0, 0, 0);
  return {start, end};
}

function datetimeLocalValue(date) {
  const valid = date instanceof Date && Number.isFinite(date.getTime()) ? date : new Date();
  const pad = (number) => String(number).padStart(2, "0");
  return [
    valid.getFullYear(),
    "-",
    pad(valid.getMonth() + 1),
    "-",
    pad(valid.getDate()),
    "T",
    pad(valid.getHours()),
    ":",
    pad(valid.getMinutes()),
  ].join("");
}

function shortDateTime(value) {
  const text = String(value || "");
  if (!text) return "";
  const datePart = text.includes("T") ? text.split("T")[0] : text.split(" ")[0];
  const timePart = shortTimeOnly(text);
  if (!datePart || !timePart) return text.slice(0, 16);
  return `${datePart.slice(5)} ${timePart}`;
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
els.navOpeningRadarButton.addEventListener("click", () => openOpeningRadarView("today"));
els.navOpeningTodayButton.addEventListener("click", () => openOpeningRadarView("today"));
els.navOpeningTrendButton.addEventListener("click", () => openOpeningRadarView("trend"));
els.navTradingButton.addEventListener("click", () => showWorkspaceView("trading-simulate"));
els.navTradingSimulateButton.addEventListener("click", () => showWorkspaceView("trading-simulate"));
els.navDataSourcesButton.addEventListener("click", () => showWorkspaceView("datasources"));
els.openRunsButton.addEventListener("click", openQueueDrawer);
els.closeScreeningDialog.addEventListener("click", closeScreeningDialog);
els.runButton.addEventListener("click", startRun);
els.summaryButton.addEventListener("click", generateSummary);
els.refreshButton.addEventListener("click", refreshAll);
els.refreshOpeningRadarButton.addEventListener("click", () => loadOpeningRadar({force: true}));
els.generateOpeningAdviceButton.addEventListener("click", generateOpeningAdvice);
els.openingTodayTab.addEventListener("click", () => setOpeningRadarSubView("today"));
els.openingLongTermTab.addEventListener("click", () => setOpeningRadarSubView("trend"));
els.openingTrendIndex.addEventListener("change", () => loadOpeningLongTermTrend({force: true}));
els.openingTrendTransform.addEventListener("change", () => loadOpeningLongTermTrend({force: true}));
els.refreshOpeningTrendButton.addEventListener("click", () => loadOpeningLongTermTrend({force: true}));
els.analyzeOpeningTrendButton.addEventListener("click", analyzeOpeningTrend);
els.toggleTradingFocusButton.addEventListener("click", toggleTradingFocusMode);
els.refreshTradingButton.addEventListener("click", () => loadTradingSimulate({force: true}));
els.tradingPairSelect.addEventListener("change", applyTradingPairSelection);
els.tradingSignalTickerInput.addEventListener("input", setTradingPairCustom);
els.tradingLongTickerInput.addEventListener("input", setTradingPairCustom);
els.tradingShortTickerInput.addEventListener("input", setTradingPairCustom);
els.createTradingInstanceButton.addEventListener("click", createTradingInstance);
els.tradingDetailStrategySelect.addEventListener("change", async () => {
  previewTradingStrategySelection();
  await updateTradingStrategySelection();
});
els.tradingDetailProfitTakeInput.addEventListener("change", updateTradingStrategySelection);
els.startTradingInstanceButton.addEventListener("click", startTradingInstance);
els.stopTradingInstanceButton.addEventListener("click", stopTradingInstance);
els.deleteTradingInstanceButton.addEventListener("click", deleteTradingInstance);
els.tradingLiveTab.addEventListener("click", () => setTradingDetailView("live"));
els.tradingBacktestTab.addEventListener("click", () => setTradingDetailView("backtest"));
els.runTradingBacktestButton.addEventListener("click", runTradingBacktest);
els.tradingBacktestDailyList.addEventListener("click", selectTradingBacktestDay);
els.detailWatchButton.addEventListener("click", toggleWatch);
els.rerunTickerButton.addEventListener("click", rerunTicker);
els.refreshTimetableButton.addEventListener("click", refreshTimetableSources);
els.shortTermTrackButton.addEventListener("click", toggleShortTermTracking);
els.summaryTab.addEventListener("click", () => setDetailTab("summary"));
els.truthTab.addEventListener("click", () => setDetailTab("truth"));
els.timetableTab.addEventListener("click", () => setDetailTab("timetable"));
els.shortTermTab.addEventListener("click", () => setDetailTab("shortterm"));
els.chartTab.addEventListener("click", () => setDetailTab("chart"));
els.workerState.addEventListener("click", openQueueDrawer);
els.latestRun.addEventListener("click", openQueueDrawer);
els.queueClose.addEventListener("click", closeQueueDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (document.body.classList.contains("trading-focus-mode")) {
      setTradingFocusMode(false);
      return;
    }
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
els.shortTermWindow.addEventListener("change", loadShortTermSnapshot);
window.addEventListener("pagehide", releaseShortTermTrackingOnPageExit);
window.addEventListener("beforeunload", releaseShortTermTrackingOnPageExit);
window.addEventListener("resize", scheduleTradingChartResize);

hydrateTickerInput();
showWorkspaceView("research");
setDetailTab("summary");
refreshAll();
setInterval(refreshRuns, 4000);

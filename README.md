# Stock Backlog Screener / Code-Beta

Code-Beta 是 `/Users/joe/stock_workspace` 里的人工投研工作台，定位是帮助人筛选、研究、关注和跟踪隐形冠军美股标的。它不负责自动下单；它输出候选池、证据链、AI 摘要、大事件跟踪和人工决策辅助，后续若要进入策略执行，应显式交给 `futu_detector` / Code-Alpha。

目标产品形态：

```text
多来源初筛 -> 候选池/列表 -> AI Summary / Truth / Timetable -> 人工关注 -> 持续跟踪 -> 辅助人工判断买卖时机
```

这是一个和 `futu_detector` 平级的独立子项目，用 Futu OpenD、SEC EDGAR/companyfacts、USAspending.gov、Launch Library、yFinance fallback 和可选 LLM 摘要来发现“隐形冠军”美股标的。

它的目标不是直接给买卖建议，而是把“自上而下找瓶颈 -> 筛选未履约订单 -> 寻找预期差”的思维模型变成可追溯、可评分、可交互的候选池生成器。

核心信息分层：

```text
raw_observations    原始信息：Futu snapshot、SEC filing、SEC companyfacts、USAspending awards、Launch Library events、yFinance fallback
information_items   信息概要：维度、来源、摘要、时间、重要度、置信度、证据 JSON
security_scores     标的评分：市值/估值/增长/持股/Backlog/RPO/信息质量
companies           标的画像：名称、市值源代码、板块/行业归属、数据源元信息
```

## 1. 安装

```bash
cd /Users/joe/stock_workspace/stock_backlog_screener
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

当前机器默认是 Python 3.9，所以依赖里把 `yfinance` 固定在 `0.2.66-1.0` 区间；更新到 Python 3.10+ 后可以再评估升级 yFinance 1.x。

如果安装时遇到 PyPI SSL EOF，可以用：

```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

## 2. PostgreSQL

本项目使用 PostgreSQL，不使用 SQLite。默认连接：

```text
postgresql://joeyang@localhost:5432/hidden_champion_screener
```

如果数据库还不存在：

```bash
createdb -h localhost -p 5432 -U joeyang hidden_champion_screener
```

初始化表结构：

```bash
python -m backlog_screener.cli init-db
```

## 3. 快速自检

不访问网络，确认代码和输出链路正常：

```bash
python -m backlog_screener.cli sample
```

输出会写到：

```text
outputs/sample_*.csv
outputs/sample_*.json
outputs/sample_*.md
```

## 4. 产品化采集

低频单线程跑一批标的，默认用 Futu OpenD + SEC，不触碰 yFinance：

```bash
python -m backlog_screener.cli ingest --no-watchlist --tickers STRL PLPC POWL
```

加入 yFinance fallback 只用于机构/内部人持股等缺口字段：

```bash
python -m backlog_screener.cli ingest --no-watchlist --tickers STRL PLPC POWL --yfinance --delay 5
```

对国防、先进制造、半导体材料、基础设施等候选，可以打开免费官方 USAspending.gov 合同检索：

```bash
python -m backlog_screener.cli ingest --no-watchlist --tickers RDW RKLB POWL --usaspending --delay 1
```

对航天、卫星、商业发射等候选，可以打开 The Space Devs Launch Library 2 未来发射窗口扫描；ticker keyword 配置文件是 `configs/launch_library_watchlist.json`：

```bash
python -m backlog_screener.cli ingest --no-watchlist --tickers RDW RKLB ASTS --launch-library --delay 1
```

对已经配置官网/IR 页的单票，可以打开 ticker-scoped 官方来源检查；配置文件是 `configs/company_official_sources.json`：

```bash
python -m backlog_screener.cli ingest --no-watchlist --tickers RDW CRDO --company-official --delay 1
```

启用 LLM 摘要前，先在本地 `.env` 写入轮换后的 key。默认 provider 仍是 MiniMax；如果要切 Gemini，把 `LLM_PROVIDER` 改成 `gemini`：

```bash
cp .env.example .env
# MiniMax: 编辑 MINIMAX_API_KEY
# Gemini: 设置 LLM_PROVIDER=gemini 并编辑 GEMINI_API_KEY
python -m backlog_screener.cli ingest --no-watchlist --tickers STRL PLPC POWL --summarize
```

MiniMax 默认使用 Anthropic-compatible endpoint，Gemini 默认使用 Google Generative Language REST endpoint：

```text
LLM_PROVIDER=minimax
MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic/v1
MINIMAX_API=anthropic-messages
鉴权头：X-Api-Key

LLM_PROVIDER=gemini
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
GEMINI_MODEL=gemini-2.5-flash
鉴权头：x-goog-api-key
```

## 4.1 用 Futu OpenD 全市场粗筛

Futu OpenD Python SDK 提供条件选股接口 `get_stock_filter`。本项目把它包装成 `seed-futu`，默认先用美股市值 `500M-4B` 做粗筛，并排除明显的 ADR、优先股、票据、权证、SPAC、OTC/PINK 等非普通股噪声：

```bash
python -m backlog_screener.cli seed-futu \
  --min-market-cap 500000000 \
  --max-market-cap 4000000000 \
  --output configs/futu_seed_us_500m_4b.csv
```

如果想先把估值也收窄：

```bash
python -m backlog_screener.cli seed-futu \
  --min-market-cap 500000000 \
  --max-market-cap 4000000000 \
  --min-pe-ttm 0 \
  --max-pe-ttm 30 \
  --output configs/futu_seed_us_500m_4b_pe30.csv
```

OpenD 条件选股有频率限制，当前 SDK 返回的限制是 30 秒最多 10 次请求；`seed-futu` 默认每页等待 `3.2` 秒，遇到限流会等待 `30` 秒后重试。

全市场深挖建议分批跑：

```bash
python -m backlog_screener.cli ingest \
  --watchlist configs/futu_seed_us_500m_4b.csv \
  --offset 0 \
  --limit 50 \
  --delay 1
```

下一批把 `--offset` 改成 `50`、`100`、`150` 继续即可。`--sec-13f` 和 `--summarize` 建议只对前几轮高分候选再打开，不要在第一轮全市场粗跑时启用。

## 5. 启动交互工具

```bash
python -m backlog_screener.cli serve --port 5055
```

浏览器打开：

```text
http://127.0.0.1:5055
```

界面支持：

```text
按板块分组列出候选标的
每个板块保留 5-10 个最高分标的，避免单一热门板块挤占 Top 100
Datasource 页面展示 source_key、来源、网站、适用范围、限流、缓存策略和通用用途说明
AI Summary 窗口：用配置的 LLM provider 总结公司业务、行业角色、推荐理由、风险和跟踪点，并缓存到信息层
查看每个标的的时间线
按信息维度筛选：company_summary / sector / valuation / growth / backlog / backlog_quality / ownership / institutional_activity / insider_activity / government_contract / quality / market
触发低频后台采集
查看原始片段、信息来源、摘要、重要度、分项评分
可选 USAspending 联邦合同证据源，用于政府订单/补贴型隐形冠军线索
可选 Launch Library 未来发射窗口证据源，用于航天/卫星类催化剂线索
```

数据源路由由 `backlog_screener/datasources.py` 集中管理：

```text
base       Futu / SEC 等基础源，默认覆盖所有 ticker
optional   yFinance / 13F / LLM Summary 等慢速或补充源，手动打开；FMP / Fintel / Ortex / Finnhub / SEC-API.io 作为 planned 候选源登记
sector     USAspending / Launch Library / FCC / 行业会议 agenda 等特定板块源，只对匹配行业或 ticker 跑
ticker     公司官网 / IR / 官方新闻源，只在该 ticker 配置了官方来源后跑
```

当前简明框架和阶段 checklist：

```text
docs/FRAMEWORK.md
docs/CHECKLIST.md
```

## 6. 旧版命令行评分

默认观察池在：

```text
configs/default_watchlist.csv
```

只用 yFinance 财务/持股数据评分：

```bash
python -m backlog_screener.cli score
```

同时扫描 SEC 最新财报文本里的 Backlog/RPO 线索：

```bash
SEC_USER_AGENT="your_name your_email@example.com" \
python -m backlog_screener.cli score --sec-text
```

## 7. 输入自己的 ticker

```bash
python -m backlog_screener.cli score --no-watchlist --tickers PLPC STRL POWL --sec-text
```

如果你想放宽 STRL 这类刚刚超过 40 亿美元市值的公司：

```bash
python -m backlog_screener.cli score --no-watchlist --tickers STRL --max-market-cap 5000000000 --sec-text
```

## 8. 让 yFinance/Yahoo Screener 先打捞候选池

只生成 ticker 列表：

```bash
python -m backlog_screener.cli seed --limit 100
```

用 Yahoo Screener 生成候选池后，再逐个拉 yFinance 详情并评分：

```bash
python -m backlog_screener.cli score --seed-yfinance --limit 100 --no-watchlist
```

再加 SEC 文本扫描：

```bash
SEC_USER_AGENT="your_name your_email@example.com" \
python -m backlog_screener.cli score --seed-yfinance --limit 100 --no-watchlist --sec-text
```

## 9. 默认过滤条件

默认值对应你给的“纯干净过滤指令”：

```text
Market Cap: 500M <= X <= 4B
Institutional Ownership: > 65%
Insider Ownership: > 5%
Quarterly Revenue YoY Growth: > 25%
Trailing P/E: 0-30
Backlog/RPO: 最新 10-Q/10-K 里必须出现文本线索，才算最终 pass
```

这些阈值都可以在命令行覆盖：

```bash
python -m backlog_screener.cli score \
  --min-market-cap 500000000 \
  --max-market-cap 4000000000 \
  --min-inst 65 \
  --min-insider 5 \
  --min-rev-growth 25 \
  --max-pe 30
```

## 10. 输出怎么看

每次运行会生成三份文件：

```text
outputs/backlog_screener_*.csv   # 适合排序、筛选、导入表格
outputs/backlog_screener_*.json  # 适合后续接入 stock_intel_hub 或其他 agent
outputs/backlog_screener_*.md    # 适合直接阅读
```

关键字段：

```text
passed                 财务硬条件 + Backlog/RPO 文本线索都通过
financial_passed       只看市值、机构持股、内部人持股、营收增速、P/E
score                  综合排序分
hard_failures          没通过的条件
positives              命中的正向条件
filing_url             被扫描的 SEC 财报链接
backlog_mentions       backlog 出现次数
rpo_mentions           RPO / Remaining Performance Obligations 出现次数
```

## 11. 数据源分工

```text
Futu OpenD
  最适合：行情、市值、P/E、P/B、成交量、52周区间、股票基础池
  限流策略：本地网关，单线程批量 snapshot

SEC EDGAR / companyfacts
  最适合：10-Q/10-K 原文、Backlog/RPO 文本、季度营收同比、毛利率、经营利润率、负债质量
  限流策略：本地缓存，低频请求，默认每个 ticker 间隔

SEC Form 4
  最适合：内部人买卖记录、净买入/净卖出金额
  限流策略：复用 SEC submissions + filing 缓存，单线程

SEC Schedule 13D/G
  最适合：5% 以上大股东/受益所有权披露，补充 ownership 维度
  限流策略：复用 SEC submissions + filing 缓存，单线程

SEC DEF 14A / 10-K ownership table
  最适合：管理层/董事高管合计持股、主要股东比例
  限流策略：复用 SEC submissions + filing 缓存，单线程

SEC 13F
  最适合：慢速扫描配置中的机构管理人持仓，补充 institutional_activity 维度
  限流策略：默认不启用；启用 --sec-13f 后按 configs/13f_managers.csv 单线程扫描

yFinance
  最适合：免费 fallback，尤其机构/内部人持股
  限流策略：默认不启用；启用时缓存 + 延迟 + 重试

MiniMax
  最适合：把 SEC 原文片段提炼成中文研究摘要、重要度、情绪、置信度
  限流策略：默认不启用；只对候选标的的关键片段单线程调用；429 时按 MINIMAX_RETRIES / MINIMAX_RETRY_WAIT_SECONDS 退避

Gemini
  最适合：作为可切换 LLM provider 生成公司画像、公告片段摘要和官网/IR 片段译写
  限流策略：默认不启用；设置 LLM_PROVIDER=gemini 后只对候选标的关键片段单线程调用；429 时按 GEMINI_RETRIES / GEMINI_RETRY_WAIT_SECONDS 退避

The Space Devs Launch Library 2
  最适合：航天/卫星类 ticker 的未来发射窗口、发射商、火箭、mission 状态和 webcast 线索
  限流策略：默认不启用；启用 --launch-library 后只对航天 scoped ticker 跑，upcoming launch JSON 缓存 6 小时
```

## 12. 注意事项

- yFinance/Yahoo Finance 数据适合做研究和候选池生成，不适合当成交易执行数据源。
- Yahoo Screener 的字段覆盖会变，代码里对机构/内部人持股比例做了 65/0.65 两种尺度的 fallback。
- Backlog/RPO 的“出现次数”只是线索，不等于质量判断。真正有价值的是增速、可转换为收入的时间、毛利率、取消条款和客户集中度。
- 这个项目只连接 Futu OpenD 行情接口，不读取真实持仓、不下单，和 `futu_detector` 的投顾/模拟交易流程保持隔离。

## 13. yFinance rate limit 怎么处理

yFinance 不是正式授权的数据 API，它底层访问 Yahoo Finance。短时间密集调用 `Ticker.get_info()` 很容易触发 `Too Many Requests`，所以本项目默认做了三件事：

```text
.cache/yfinance/      本地缓存每个 ticker 的 yFinance 指标
--yf-delay 1.5        每个 ticker 之间默认等 1.5 秒
--yf-retries 1        遇到 rate limit 后重试 1 次
--yf-retry-wait 30    第一次重试前等 30 秒
```

更稳的跑法：

```bash
python -m backlog_screener.cli score \
  --tickers PLPC STRL POWL \
  --no-watchlist \
  --sec-text \
  --yf-delay 5 \
  --yf-retries 2 \
  --yf-retry-wait 60
```

如果刚被 Yahoo 限流，先别反复重跑，等 30-60 分钟再试。已经成功拉过的数据会进 `.cache/yfinance/`，下一次默认 24 小时内复用缓存，不会重复打 Yahoo。

强制刷新缓存：

```bash
python -m backlog_screener.cli score --tickers STRL --no-watchlist --yf-force-refresh
```

如果要稳定做生产级选股，建议把 yFinance 只作为免费候选池来源，核心财务数据改接付费/正式 API，比如 Financial Modeling Prep、Polygon、Finnhub、Tiingo，或者 SEC companyfacts + 13F/持股数据源。

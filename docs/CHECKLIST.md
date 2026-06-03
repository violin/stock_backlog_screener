# Phase 1-3 Checklist

## Phase 1: 数据源扩展

- [x] Futu OpenD 继续只负责行情、市值、估值类 snapshot。
- [x] Futu OpenD 增加 `owner_plate` 板块/行业归属，用于产品分组。
- [x] Futu OpenD 增加 `capital_distribution`、`capital_flow`、历史 K 线，形成独立 `attention_flow` 维度。
- [x] SEC 10-Q/10-K 继续扫描 Backlog/RPO 文本和金额线索。
- [x] SEC companyfacts 增加自由现金流、应收、库存、权益等财务质量字段。
- [x] SEC Form 4 采集内部人交易并落入 `insider_activity` 维度。
- [x] SEC Schedule 13D/G 采集 5% 以上大股东披露并落入 `ownership` 维度。
- [x] SEC DEF 14A / 10-K ownership table 解析管理层/董事高管持股。
- [x] 新增可选 SEC 13F 慢速扫描，配置文件为 `configs/13f_managers.csv`。
- [x] yFinance 保持默认关闭，只作为限流友好的 fallback。
- [x] MiniMax 保持默认关闭，只在显式 `--summarize` 或页面勾选后使用。

验证命令：

```bash
python -m backlog_screener.cli init-db
python -m backlog_screener.cli ingest --no-watchlist --tickers STRL PLPC POWL --delay 0.5
python -m backlog_screener.cli ingest --no-watchlist --tickers PLPC --no-futu --sec-13f --delay 0.5
```

## Phase 2: 评分模型 v2

- [x] 模型版本更新为 `hidden_champion_v3`。
- [x] 分项评分覆盖市值适配、估值、增长质量、订单质量、所有权对齐、财务质量、信息质量。
- [x] 新增 `attention_flow` 独立分项：主力买卖比高且近期涨幅小加分，近期涨幅过大时扣分。
- [x] 增加关键维度缺失扣分，避免只有少量信息时总分虚高。
- [x] 保留旧 UI/API 兼容字段：`size`、`growth`、`ownership`、`backlog_rpo`。
- [x] 单元测试覆盖完整候选画像的 A 档评分。

验证命令：

```bash
python -m compileall backlog_screener tests
python -m unittest discover -s tests
```

## Phase 3: 产品化交互工具

- [x] Flask Dashboard 展示 Ranked Candidates、分项评分、缺失维度、信息时间线。
- [x] 时间线支持按 dimension 筛选。
- [x] 时间线支持 `attention_flow` 资金/关注度维度筛选。
- [x] 证据区展示 `evidence` JSON，保留原始信息和评分来源。
- [x] 页面采集表单支持 yFinance、13F、MiniMax 开关。
- [x] API 支持候选池、单标的时间线、采集运行状态、后台触发采集。
- [x] API 支持按板块分组候选池，每个板块保留 5-10 个最高分标的。
- [x] Dashboard 支持板块分组列表、板块内排名、Per Sector 选择。
- [x] Dashboard 支持 AI Summary 窗口，按公司业务、行业角色、推荐理由、风险、跟踪点分块展示。
- [x] API 支持 `GET/POST /api/ticker/<ticker>/summary`，MiniMax prompt 生成后缓存为 `company_summary` 信息维度。

验证命令：

```bash
python -m backlog_screener.cli serve --port 5055
curl -s http://127.0.0.1:5055/api/candidates
curl -s 'http://127.0.0.1:5055/api/ticker/STRL?dimension=ownership'
curl -s http://127.0.0.1:5055/api/runs
```

## 验证记录

- 静态检查：`python -m compileall backlog_screener tests` 通过。
- 单元测试：`python -m unittest discover -s tests` 通过，10 tests OK。
- PostgreSQL 核心采集：run `11`，`STRL PLPC POWL`，状态 `DONE`。
- run `11` 原始来源覆盖：`futu_opend` 3、`sec_edgar` 3、`sec_companyfacts` 3、`sec_form4` 3、`sec_beneficial_ownership` 3、`sec_proxy_ownership` 3。
- run `11` 最新候选评分：`POWL 55.80 C`，`STRL 54.80 C`，`PLPC 47.28 C`。
- SEC 13F 可选慢速验证：run `6`，`PLPC`，检查 8 个配置机构，匹配 6 个管理人、27 条持仓行。
- MiniMax 配置验证：本地 key 可读取；实时 API smoke 返回 HTTP 429，采集层已验证可 fallback 到 heuristic，不中断 run。
- Dashboard 服务：`http://127.0.0.1:5056` 已启动。
- Dashboard API smoke：`/api/candidates`、`/api/ticker/STRL?dimension=ownership`、`/api/runs` 通过。
- 时间线去重验证：`STRL ownership` API 返回 1 条去重后的 13D/G 信息，不再重复展示旧 run。
- 板块归属验证：run `13`，`STRL PLPC POWL`，仅 OpenD 采集，状态 `DONE`。
- OpenD `owner_plate` 入库验证：`STRL -> Engineering & Construction`，`PLPC/POWL -> Electrical Equipment & Parts`。
- 分组候选 API 验证：`/api/candidates/grouped?min_score=0&per_sector=5` 返回按板块分组结果。
- Dashboard 渲染验证：`http://127.0.0.1:5056` 显示板块分组候选列表，浏览器控制台无 error/warning。
- Summary 窗口验证：页面展示 `AI Summary`、`生成摘要` 按钮、`company_summary` 维度筛选项，浏览器控制台无 error/warning。
- MiniMax 实时生成验证：`POST /api/ticker/POWL/summary` 链路打通，当前外部服务返回 HTTP `429`，未写入缓存摘要。
- Run Queue 验证：页面展示 Current/Pending/Completed/Failed；轻量 run `15` 完成后队列显示 `RKLB`、`POWL` 已完成。
- 视图过滤器位置验证：`Score Filter`、`Top / Sector` 位于 Ranked Candidates 内部；`Timeline Filter` 位于右侧详情面板；Ticker 输入刷新后保留本地值。
- Queue 抽屉验证：右上角 `IDLE/RUN` 状态按钮可唤出右侧 Run Queue 抽屉；原页面中部横向 queue 面板已移除；浏览器控制台无 error/warning。
- Run Monitor 验证：`/api/runs` 增加 PostgreSQL-backed `monitor`，右侧抽屉展示 CLI/后台/Web run 的状态、进度条、维度完成数、错误观测数和最近 run；避免 CLI 任务运行时页面队列误显示为空。
- Futu 主力资金实测：`POWL` 返回 `capital_distribution`、20 条日级 `capital_flow`、80 条日 K，能计算特大+大单买卖比与 5/20/60 日涨幅。
- `attention_flow` 入库验证：run `18`，`POWL`，时间线写入 `POWL main-money attention and pullback risk`；v3 评分中 `attention_flow=-3.0`。
- Dashboard `attention_flow` 验证：页面存在 `Attention / 关注/资金` 分项、`Attention Flow` 时间线筛选项；切到 `POWL` 后能展示资金/涨幅证据；浏览器控制台无 error/warning。
- 默认 watchlist 全链路验证：run `19`，14 个标的，Futu + SEC 全部完成；`attention_flow`、market、sector、valuation、backlog、growth、quality、insider_activity 均覆盖 14/14。
- Futu-only 刷新验证：run `20`，14 个标的，刷新行情/资金/板块并复用已有 SEC 信息重新评分；榜首为 `IESC 68.0 B`、`TPC 61.8 C`、`MTZ 59.0 C`。
- `attention_flow` 规则校正：有买卖比时必须买卖比足够高才可标记 `quiet_accumulation`；`ACM` 从旧标签修正为 `neutral`，并修复时间线同事件优先展示最新信息项。
- 限流配置沉淀：新增 `configs/rate_limits.json`，记录 Futu `get_stock_filter` 10 次/30 秒、`get_capital_flow` 30 次/30 秒、`owner_plate` ETF-like fallback、SEC/yFinance/MiniMax 推荐 delay/retry。
- Futu K 线额度降级：`request_history_kline` 可能触发 historical candlestick quota；`attention_flow` 已改成保留主力资金/资金流，近期涨幅缺失时在 summary/evidence 中标注，不再整条丢弃。
- 500M-1B Futu 粗筛完成：`configs/futu_seed_us_500m_1b.csv` 共 502 个 ticker；market/valuation/sector/attention_flow 覆盖 502/502，评分 502/502。
- 500M-1B sector shortlist 深挖完成：严格限定在 502 ticker 内生成 `configs/futu_seed_us_500m_1b_sector_shortlist.csv`，56 个 ticker，SEC 深挖与重评分 56/56；导出 `outputs/futu_500m_1b_sector_shortlist_sec_deepdive_20260528_231646.csv`。
- SEC transient retry：`SecClient` 对 SEC HTTP/Archive 下载增加 2 次短重试；offset 60 初次 `run 42` 遇到 `SSLEOFError` 后，重跑 `run 43` 和补跑 `run 44` 均完成。
- MiniMax 配置优先级修正：`load_dotenv(..., override=True)`，确保 `.env` 里的 `MINIMAX_API_KEY` 覆盖旧进程环境变量；Top 5 `GTM/ETD/OSPN/JBSS/MLAB` company summary 生成成功并写入信息层。

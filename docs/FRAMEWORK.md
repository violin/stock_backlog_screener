# 隐形冠军选股器当前框架

本项目是 `futu_detector` 的平级子项目，只做美股“隐形冠军”候选池发现，不读取真实持仓、不下单。

## 核心推演

```text
宏观瓶颈/产业变化
  -> 中小市值供应链公司
  -> Backlog/RPO 或订单可见性
  -> 财务质量和所有者结构验证
  -> 信息分层、评分、排序
```

评分不是直接买卖建议，而是把标的放进“值得进一步人工研究”的优先级队列。

## 信息分层

```text
raw_observations
  原始信息层：Futu snapshot、SEC filing 原文、companyfacts JSON、Form 4、13D/G、DEF 14A、可选 13F。

information_items
  信息概要层：每条信息带 dimension、source_key、summary、raw_excerpt、importance_score、confidence_score、evidence JSON。

security_scores
  标的评分层：聚合最新信息，按模型版本计算总分、分项分、缺失维度、解释文本。
```

## 数据源分工

接口级限流记录在 `configs/rate_limits.json`。大批量任务先看这个文件，再决定 batch size、delay、retry wait；特别是 Futu `get_capital_flow` 已实测为 30 次/30 秒量级，不能并发。

数据源注册和适用范围集中在 `backlog_screener/datasources.py`：

```text
base       基础数据源，默认对所有 ticker 跑，例如 Futu OpenD、SEC filings/companyfacts/Form 4/ownership。
optional   慢速或补充数据源，手动打开，例如 yFinance、SEC 13F、MiniMax；FMP、Fintel、Ortex、Finnhub、SEC-API.io 已作为 planned 候选源登记。
sector     特定板块数据源，只对匹配 sector/industry/ticker 的公司跑，例如 USAspending；Launch Library、FCC、行业会议 agenda 已预留为 planned。
ticker     单 ticker 官方来源，只在 company metadata 配置 official_sources 后跑，例如公司官网、IR 新闻、产品/发射日历。
```

```text
Futu OpenD
  条件选股粗筛、行情、市值、P/E、P/B、成交量、板块/行业归属、资金分布、资金流向、近期涨幅等低频 snapshot。

SEC 10-Q/10-K
  Backlog/RPO 文本线索、金额线索、关键片段。

SEC companyfacts
  季度收入同比、利润率、现金流、负债、应收/库存变化。

SEC Form 4
  内部人近期买卖，估算净买入/净卖出。

SEC 13D/G
  5% 以上大股东或受益所有权披露。

SEC DEF 14A / 10-K ownership table
  管理层/董事高管合计持股、主要股东比例。

SEC 13F
  可选慢速扫描配置中的机构管理人持仓，补充机构持股信号。

USAspending.gov
  可选免费官方联邦合同 API，用于 aerospace / defense / semiconductor materials / infrastructure / advanced manufacturing 等候选的政府订单和补贴型背书。只作为 order_quality 的加分证据，不把没有政府合同当作扣分项。

yFinance
  默认关闭，只作为免费 fallback，主要补机构/内部人持股字段。

MiniMax
  默认关闭；使用 Anthropic-compatible `/anthropic/v1/messages` 与 `X-Api-Key`；用于关键 SEC 片段概要，也用于公司 Summary 窗口，基于已采集证据总结业务、行业角色、推荐理由、风险和跟踪点。
```

## v2 评分模型

当前模型版本：`hidden_champion_v3`。

```text
eligibility             市值区间是否符合中小型隐形冠军画像
valuation               P/E 是否还没有被充分重估
growth_quality          收入同比，以及应收/库存是否没有明显恶化
order_quality           Backlog/RPO 文本强度、RPO 线索、金额/收入比例
government_contract     USAspending 联邦合同奖项，作为订单可见性和战略背书补充
ownership_alignment     内部人/管理层持股、机构持股、大股东、内部人交易、13F
financial_quality       毛利率、经营利润率、净利率、自由现金流率、杠杆
attention_flow          主力买卖比、近 20/60 日涨幅和资金拥挤度；独立于基本面
information_quality     来源覆盖度和最高重要度
missing_dimensions      对关键缺失维度扣分，防止信息不完整时虚高
```

`attention_flow` 不是基本面质量分，而是市场行为标签：

```text
quiet_accumulation   特大+大单买入/卖出比高，但近 20 日涨幅不大，更接近低关注度吸筹
crowded_momentum     主力买入强，但近 20 日涨幅已经过大，偏拥挤交易和回撤风险
distribution_risk    近期涨幅较高但主力买卖比不足，偏分歧或派发风险
neutral              资金和价格扩散暂未形成清晰组合信号
```

## 交互工具

本地启动：

```bash
python -m backlog_screener.cli serve --port 5055
```

页面能力：

```text
候选标的按板块分组展示
每个板块单独取 5-10 个最高分标的，形成 sector-balanced Top candidates
查看分项评分和缺失维度
查看 AI Summary：MiniMax prompt 生成并缓存 company_summary 信息维度
按信息维度筛选时间线，包含 sector、attention_flow 维度
查看原始片段、来源、概要、重要度、证据 JSON
后台触发低频采集，可选 yFinance、13F、MiniMax
右上角状态按钮打开 Run Monitor，读取 PostgreSQL 的 collection_runs，展示 CLI/后台/Web run 的状态、进度、维度完成数、错误观测和最近活动
```

## 全市场粗筛

先用 OpenD 条件选股接口按市值生成候选池：

```bash
python -m backlog_screener.cli seed-futu --output configs/futu_seed_us_500m_4b.csv
```

然后分批进入深挖流水线：

```bash
python -m backlog_screener.cli ingest --watchlist configs/futu_seed_us_500m_4b.csv --offset 0 --limit 50 --delay 1
```

这保持了数据源分层：OpenD 只负责全市场低成本粗筛和行情估值，SEC/ownership/LLM 只消耗在被打捞出来的候选池上。

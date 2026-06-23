# Intraday Strategy Discovery Framework

## 1. Objective

Build a repeatable research system that discovers, explains, validates, and
tracks short-term strategies for one stock or one signal/long/bear ticker pair.

The system is not expected to find a permanently optimal rule. Its job is to
find strategies that are:

- profitable after estimated spread and slippage;
- supported by enough independent trades and trading days;
- stable across time windows, volatility regimes, and nearby parameter values;
- understandable in market terms;
- active enough to be useful without forcing trades.

The working frequency target is roughly 2-3 completed operations per session.
This is a preference, not a hard requirement.

## 2. Research Unit and Data

### Primary unit

- Regular US session only: 09:30-16:00 America/New_York.
- Default research bar: 3 minutes.
- Source bars: Futu OpenD 1-minute OHLCV, resampled locally.
- Separate signal ticker and execution tickers when a leveraged/inverse pair is
  used.

### Minimum useful sample

- First pass: 30 complete sessions.
- Candidate promotion: at least 60 complete sessions.
- Stability review: preferably 90-120 sessions spanning more than one
  volatility regime.

Partial sessions, market holidays, duplicate bars, zero-volume bars, and
extended-hours rows are recorded and handled explicitly.

## 3. Feature Matrix

Every 3-minute decision point receives only information available at that time.
Future-return columns are generated separately and may only be used as labels
or evaluation targets.

### Price and candle geometry

- OHLC, volume, turnover and VWAP.
- 3m/6m/9m/15m/30m/60m returns.
- candle body, total range, upper wick and lower wick;
- gap, true range and ATR-normalized candle size;
- distance from session high/low and rolling 30-minute high/low.

### Trend

- SMA 5/10/20/50;
- EMA 5/9/21/50;
- fast/slow spreads;
- 3-bar and 5-bar slopes;
- price distance from each average;
- VWAP distance and VWAP slope.

### Momentum

- RSI 6/14;
- KDJ 9 K/D/J;
- MACD DIF/DEA/histogram and histogram change;
- stochastic %K/%D;
- rate of change and acceleration.

### Volatility and location

- ATR 14 and ATR percentage;
- Bollinger midpoint, bandwidth, z-score and percent-b;
- rolling realized volatility;
- rolling range position;
- opening-range 15-minute distance;
- volatility compression/expansion state.

### Volume and participation

- volume ratio and z-score versus recent bars;
- cumulative session volume;
- intraday volume seasonality adjustment;
- OBV and OBV slope;
- price-volume divergence;
- money-flow proxy where turnover is available.

### Context

- minutes from open and minutes to close;
- first hour, midday and final hour flags;
- day-of-week;
- prior-session gap;
- trend/range regime;
- high/normal/low volatility regime.

The initial implementation should favor transparent features. Feature count can
grow, but highly collinear variants must be grouped so that ten versions of the
same moving average do not look like ten independent discoveries.

## 4. Peak and Trough Labels

The arrows on a chart are not always single points. A top may be a plateau,
double top, or noisy distribution area; a bottom may be a flush followed by
several retests. The label is therefore a **turning zone**, not a perfect tick.

### Zone construction

1. Find local high/low candidates inside a centered window.
2. Require prominence relative to ATR, not a fixed dollar move.
3. Merge adjacent candidates when:
   - they are within a small ATR-normalized price tolerance; and
   - they occur within a small number of bars.
4. Store:
   - zone start/end;
   - representative extreme;
   - duration;
   - prominence in ATR units;
   - confirmed reversal magnitude.

The calibrated default for 3-minute CRDO research is a centered 5-bar window,
2.0 ATR minimum prominence, 0.18 ATR plateau tolerance, and a 2-bar merge gap.
On the initial 30-session sample this reduced representative pivots from about
20% of bars to about 6%, removing many visually insignificant wiggles while
retaining flat and multi-bar turns.

### Leakage control

Centered extrema and reversal confirmation use future bars, so they are labels
for research only. A strategy may use features from the bar before the zone or
from a causal confirmation bar after the turn, but it may never use the final
zone label in live decisions.

We distinguish two research questions:

- **anticipation:** which features occur before a turning zone?
- **confirmation:** which causal changes show that the turn has probably
  started?

The second is often more tradable even if it enters after the exact extreme.

## 5. Feature Mining

### Univariate screen

For peak and trough zones:

- compare event medians with the non-event baseline;
- calculate standardized differences;
- calculate event-rate lift by feature quantile;
- inspect monotonicity across quantiles;
- reject features whose sign changes arbitrarily across folds.

### Rule generation

Generate transparent one-, two-, and at most three-condition rules from robust
quantile thresholds. Examples:

- oversold + improving momentum;
- lower Bollinger location + VWAP reclaim;
- overbought burst + momentum rollover;
- opening-range breakout + volume confirmation.

Rules are evaluated with non-overlapping trades, cooldowns, realistic costs,
and explicit exits. Large brute-force combinations are avoided because they
produce attractive historical accidents.

### Statistical guardrails

For each candidate record:

- trade count and active day count;
- trade win rate and Wilson lower confidence bound;
- profitable-day rate;
- total and average PnL;
- profit factor;
- maximum drawdown;
- average trades per active day;
- train/test degradation;
- parameter-neighborhood stability.

A 70% observed win rate is not enough by itself. A 7/10 result is weak evidence;
a lower but stable rate with positive expectancy and many independent trades
may be more useful.

## 6. Validation

### Walk-forward design

- chronological train/validation/test splits;
- expanding or rolling walk-forward folds;
- purge overlapping label horizons around split boundaries;
- never tune thresholds on the final test fold.

### Regime validation

Each candidate is split by:

- trend versus range;
- high versus low ATR;
- first hour, midday and final hour;
- above versus below VWAP;
- gap-up, gap-down and flat open.

The goal is not a universal strategy. The goal is to identify where a strategy
works and when it should be disabled.

### Promotion levels

1. **Experiment**
   - mechanically valid;
   - not enough evidence.
2. **Candidate**
   - positive train and validation expectancy;
   - positive validation PnL;
   - acceptable frequency.
3. **Watch**
   - survives multiple walk-forward folds;
   - no single day dominates PnL;
   - nearby thresholds remain profitable.
4. **Reference**
   - sample size is meaningful;
   - test profit factor and drawdown are acceptable;
   - financial interpretation is coherent.

No status implies permission for real trading.

## 7. Working Acceptance Criteria

The user target is approximately 70% relative win rate, but candidate promotion
uses several gates together:

- positive out-of-sample total PnL;
- profit factor greater than 1.2 in validation and preferably 1.3+ in test;
- enough trades to make the win rate meaningful;
- positive profitable-day rate;
- no extreme concentration in one or two sessions;
- average frequency reasonably close to 2-3 operations per day;
- stable result around nearby thresholds.

Seventy percent is treated as a stretch target, not a threshold to optimize at
all costs.

## 8. Financial Interpretation

Every mined rule needs a market explanation:

- Is it mean reversion after liquidity exhaustion?
- Is it trend continuation with participation?
- Is it an overbought exit rather than a short-entry signal?
- Is the signal merely restating price movement?
- Does it still make sense after spread, slippage, and leverage decay?

Rules without a plausible mechanism may remain experiments but should not be
promoted solely because of a high backtest score.

## 9. Product Integration

The strategy selector should show:

- strategy name and research status;
- buy conditions;
- sell/exit conditions;
- risk/avoid conditions;
- most recent backtest period;
- day win rate and day count;
- trade win rate and trade count;
- total PnL and profit factor;
- average operations per day.

Backtest results are stored per ticker-pair and per strategy. Changing strategy
does not require creating another instance.

## 10. Initial Research Queue

### Generic baselines

- RSI Extreme: RSI rotation with independent take profit.
- RSI Rotation: RSI rotation without independent take profit.

### CRDO experiments from the existing 30-session study

- Rebound confirmation:
  `RSI6 <= 20`, 15-minute return `<= -2%`, and MACD histogram improving.
- Peak/avoid condition:
  `KDJ J >= 80` and 3-minute return `>= 1%`.

The CRDO rebound result is a candidate, not a reference strategy: the existing
train and test samples each contain only nine trades. The next iteration must
increase the history and use rolling walk-forward validation.

### CRDO calibrated 83-session study

The first reusable run covered 83 sessions from 2026-02-23 through 2026-06-22
and 10,790 three-minute bars. The stricter turning-zone definition found 315
troughs and 301 peaks, or about 5.7% of bars.

The strongest recent long-side pattern was:

- volume z-score `>= 1.66`;
- Bollinger percent-b `<= 0.099` (or equivalent z-score `<= -1.60`).

It resembles liquidity exhaustion: an unusually active selloff reaches the
lower volatility envelope and then mean-reverts. It produced 38 recent test
trades, 60.5% trade wins, +8.30% signal-side net return, profit factor 1.87,
and 1.81 trades per active day. It is still rejected because the earlier
training period lost 5.66% with profit factor 0.81. This is useful evidence of
a regime-dependent edge, not a stable strategy.

The strongest two-sided mining result was a short-direction experiment:

- MACD histogram `<= -0.1911`;
- EMA9/EMA21 spread `<= -0.25%`.

It was positive in both chronological partitions, but only marginally:
99 train trades at +0.79% and profit factor 1.02; 90 test trades at +5.60% and
profit factor 1.13. Frequency was 3.91 trades per active day and the test win
rate was 43.3%. The economic reading is bearish continuation after trend
separation, but the edge is too thin after costs and is not promoted.

No mined CRDO rule currently qualifies for the strategy selector. Short-side
research returns are based on the signal ticker's inverse return; promotion
requires a second backtest using the actual bear ticker's bid/ask history.

### Existing LITE pair baselines

Both current RSI baselines were compared over the same 22 trading days:

- RSI Extreme: 40.9% profitable days, 58.7% trade wins, 121 trades,
  5.50 trades/day, and -$535.45.
- RSI Rotation: 40.9% profitable days, 58.3% trade wins, 120 trades,
  5.45 trades/day, and -$498.47.

Both fail the PnL and frequency gates despite trade win rates near 59%. This is
the practical reason win rate cannot be used without payoff and trade-count
context.

## 11. Industry Strategy Archetypes

The research engine now separates a strategy's **economic mechanism** from its
parameter values. The same compact parameter grid is evaluated unchanged on
CRDO, SPCX, and AAOI before any ticker-specific tuning.

### Opening-range breakout

- Define the first 15 or 30 minutes as the price-discovery range.
- Enter only on a later close through the range, with volume and EMA alignment.
- Test both long and short directions.

This is inspired by opening-range breakout practitioner research, but working
paper results are treated as hypotheses rather than established universal
effects. The exchange open is structurally special because the core opening
auction begins the 09:30-16:00 ET session.

### Late-day intraday momentum

- Measure the first 30-minute return.
- Test the same direction near the start of the final 30 minutes.
- Require elevated realized volatility.

The academic result was documented primarily on liquid market ETFs, so its
application to single volatile stocks is a transfer test, not a direct
replication.

### Liquidity-exhaustion reversal

- Require an extreme Bollinger location and RSI state.
- Require abnormal volume.
- Optionally require MACD histogram improvement before entry.

The mechanism is compensation for providing liquidity after temporary order
imbalance. The expected return should be regime-dependent, not constant.

### Bollinger squeeze breakout

- Identify bandwidth in the stock's low historical intraday quantiles.
- Wait for a break of the previous local range.
- Require volume and trend confirmation.

Bollinger Bands define relative high and low and should be combined with
independent confirmation. A squeeze forecasts possible volatility expansion,
not its direction.

### VWAP reclaim

- Detect a causal cross back through session VWAP.
- Require improving EMA slope, bounded RSI, and participation.

VWAP is first an execution benchmark based on historical and realized volume
patterns. Its use here as a support/resistance anchor is explicitly labeled a
practitioner hypothesis and must earn its status only through the backtest.

### Trend pullback reclaim

- Require aligned EMA9, EMA21, and EMA50.
- Enter when price reclaims EMA9 after a controlled pullback.
- Bound RSI to avoid chasing the most extended bars.

This is a transparent trend-following archetype rather than a claim tied to one
specific academic anomaly.

### Deferred: relative-value pairs

Pairs trading has stronger academic foundations than many indicator rules, but
it requires synchronized prices, hedge-ratio estimation, and spread
stationarity checks. It is intentionally deferred until benchmark/peer data is
added; it cannot be evaluated from one ticker's OHLCV alone.

Primary references:

- Gao, Han, Li, and Zhou, [Intraday Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2552752).
- Nagel, [Evaporating Liquidity](https://www.nber.org/papers/w17653).
- Gatev, Goetzmann, and Rouwenhorst, [Pairs Trading](https://academic.oup.com/rfs/article-abstract/19/3/797/1646694).
- Zarattini and Aziz, [Opening Range Breakout study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284).
- John Bollinger, [official Bollinger Band rules](https://www.bollingerbands.com/bollinger-band-rules).
- NYSE, [core session and auction timing](https://www.nyse.com/trade/trading-information).
- Nasdaq, [VWAP execution algorithm description](https://www.nasdaq.com/docs/2020/06/08/Nasdaq-Exchange-Clearing-Services-AB-Execution-Algorithms-User-Guide-2.7.pdf).

## 12. From One Stock to Any Stock

The intended product is not one fixed threshold set that claims to trade every
stock. It is an adaptation pipeline:

1. verify sufficient regular-session history and executable liquidity;
2. calculate causal, volatility-normalized features;
3. evaluate the same strategy families and small parameter neighborhoods;
4. use chronological holdout and expanding walk-forward folds;
5. classify results as transferable, ticker-specific, or rejected;
6. calibrate ticker-specific thresholds only after the family survives;
7. validate on actual long/bear execution tickers and bid/ask assumptions;
8. allow the correct result to be **no executable strategy**.

The primary objective is now individual-stock strategy discovery. Cross-stock
portability is optional context and is not required for a ticker strategy to
advance. A strategy may be excellent for one stock and unsuitable for another.

Cross-ticker status meanings:

- `portable_candidate`: positive on every covered stock with acceptable median
  profit factor and frequency;
- `portable_experiment`: positive train/test behavior on at least two-thirds of
  covered stocks;
- `ticker_specific`: coherent on one stock only;
- `reject`: not reliable on the covered set.

## 13. CRDO / SPCX / AAOI Industry-Archetype Results

The first cross-ticker run used the same 3-minute feature definitions, next-bar
entry, 10 bps round-trip cost, conservative same-bar stop priority, compact
parameter grids, and expanding walk-forward design.

### Coverage gate

- CRDO: 83 sessions, 10,790 bars, median ATR about 0.48%.
- AAOI: 83 sessions, 10,790 bars, median ATR about 0.76%.
- SPCX: only 9 sessions and 1,114 bars available from Futu, so it remains in
  the research record but is excluded from portability claims.

This is an important valid output of the general system: a new or
short-history stock must return **insufficient evidence**, not a strategy based
on one winning trade.

### CRDO research leader: liquidity-exhaustion rebound

Conditions:

- Bollinger percent-b `<= 0.10`;
- RSI6 `<= 40`;
- volume z-score `>= 1.0`;
- no delayed MACD confirmation in the current best variant.

Results:

- train: 65 trades, 49.2% win rate, +1.45%, PF 1.06;
- test: 31 trades, 61.3% win rate, +7.26%, PF 1.93;
- profitable test days: 60%;
- test frequency: 1.55 trades per active day;
- walk-forward: 3/4 positive folds;
- family-neighborhood stability: 1/4 tested parameter variants passed the
  robust sample/PF gates.

Interpretation: the recent mean-reversion payoff is meaningful, but the
training expectancy and neighborhood stability are weak. It remains an
experiment rather than an executable reference strategy.

### AAOI research leader: Bollinger squeeze breakout

Conditions:

- Bollinger bandwidth at or below its rolling 30th percentile;
- long break of the previous local range;
- EMA9 above EMA21;
- current volume ratio `>= 1.0` (the `>= 1.3` neighbor also remained positive).

Results for the `>= 1.0` variant:

- train: 42 trades, 42.9% win rate, +1.66%, PF 1.08;
- test: 20 trades, 50.0% win rate, +5.33%, PF 1.64;
- profitable test days: 62.5%;
- test frequency: 1.25 trades per active day;
- walk-forward: 4/4 positive folds;
- family-neighborhood stability: 2/4 variants passed robust gates.

Interpretation: AAOI's higher intraday volatility makes volatility expansion
more promising than CRDO-style lower-band mean reversion. The train PF is still
too thin for promotion, but this is the strongest follow-up candidate.

### Stocks-in-Play opening-range breakout

ORB was reimplemented with cross-session features rather than ordinary
20-bar volume:

- opening 15/30-minute range;
- first-15-minute volume relative to the same opening window over prior
  sessions;
- optional absolute overnight gap of at least 1%;
- EMA trend confirmation.

Several recent test slices were positive on both CRDO and AAOI, but samples
were only 4-11 trades and walk-forward results were inconsistent. Therefore
ORB is a research lead, not yet a portable candidate.

### Cross-stock conclusion

No strategy variant qualified as portable across the eligible stocks. The
current evidence instead supports ticker-to-family adaptation:

- CRDO -> liquidity-exhaustion mean reversion;
- AAOI -> volatility-compression breakout;
- SPCX -> wait for sufficient history.

This is consistent with the user's premise that the best thresholds and even
the best mechanism differ by stock. The generalizable asset is the research
pipeline and promotion discipline, not one universal indicator rule.

## 14. RKLB and MRVL Individual Strategy Results

Both stocks passed the data gate with 83 sessions and 10,790 three-minute bars
from 2026-02-23 through 2026-06-22. Entry rules were mined on the chronological
training segment. Exit parameters were then chosen on training data only and
evaluated on the untouched final test segment. Six fixed 14-session blocks are
reported as temporal-stability diagnostics; they are not additional
independent holdouts.

### RKLB: watch, current regime disabled

The best surviving structure is an oversold rebound:

- EMA9/EMA21 spread `<= -0.48%`;
- Bollinger percent-b `<= 0.0845`;
- long on the next 3-minute open;
- target 1.5%, stop 1.0%, maximum hold 8 bars;
- maximum 2 trades per day.

Results:

- train: 52 trades, 69.2% win, +18.96%, PF 2.78;
- test: 19 trades, 63.2% win, +1.54%, PF 1.21;
- test profitable-day rate: 61.5%;
- frequency: 1.46 trades per active day;
- entry threshold neighbors: 3/3 positive;
- time blocks: 5/6 positive.

The latest block, 2026-06-03 through 2026-06-22, lost 1.89% with PF 0.70.
Therefore the rule is `Watch`, not an active paper candidate. The result
suggests that RKLB mean reversion worked historically but weakened in the
current regime. Before activation it needs a causal regime-enable condition
and an execution backtest using RKLX/RKLZ bid/ask history.

### MRVL candidate 1: same-time volume shock below VWAP

Entry:

- volume versus the same intraday time over prior sessions `>= 2.65x`;
- price `>= 0.89%` below session VWAP;
- long on the next 3-minute open.

Execution:

- target 2.0%, stop 0.8%, maximum hold 5 bars;
- maximum 3 trades per day.

Results:

- train: 52 trades, 65.4% win, +13.15%, PF 2.33;
- test: 35 trades, 51.4% win, +8.68%, PF 1.61;
- test profitable-day rate: 73.3%;
- frequency: 2.33 trades per active day;
- threshold neighbors: 3/3 positive;
- all 6 time blocks positive;
- latest block: +4.12%, PF 1.42.

Financial interpretation: abnormal participation below the session's
volume-weighted anchor may represent temporary liquidity pressure rather than
new equilibrium information. The moderate win rate works because average
payoff and loss control are favorable.

### MRVL candidate 2: volume shock after negative trend separation

Entry:

- EMA9/EMA21 spread `<= -0.28%`;
- same-time relative volume `>= 2.65x`;
- long on the next 3-minute open.

Execution:

- target 2.0%, stop 1.0%, maximum hold 5 bars;
- maximum 2 trades per day.

Results:

- train: 33 trades, 69.7% win, +8.35%, PF 2.20;
- test: 25 trades, 60.0% win, +7.59%, PF 1.81;
- test profitable-day rate: 64.3%;
- frequency: 1.79 trades per active day;
- threshold neighbors: 3/3 positive;
- all 6 time blocks positive;
- latest block: +5.82%, PF 1.87.

This is the cleaner MRVL candidate because its frequency is closer to the
desired range and its latest block remains healthy.

### MRVL enlarged-range frozen validation

The two long candidates were then frozen without changing their entry
thresholds, exits, cooldowns, daily trade caps, or 10 bps cost assumption and
retested over 251 sessions from 2025-06-23 through 2026-06-22.

Primary, same-time volume shock below VWAP:

- full range: 210 trades, 51.0% win, +19.85%, PF 1.33;
- profitable-day rate: 59.2%, with 2.04 trades per active day;
- 8/13 fixed 20-session blocks positive;
- pre-discovery 168-session backcast: 120 trades, 45.0% win, -1.48%,
  PF 0.96;
- original 83-session discovery window: 90 trades, 58.9% win, +21.33%,
  PF 1.88;
- latest 60 sessions: 69 trades, 59.4% win, +19.25%, PF 1.94.

Secondary, same-time volume shock after negative EMA separation:

- full range: 140 trades, 53.6% win, +12.01%, PF 1.27;
- profitable-day rate: 58.2%, with 1.54 trades per active day;
- 8/13 fixed 20-session blocks positive;
- pre-discovery 168-session backcast: 79 trades, 45.6% win, -3.70%,
  PF 0.86;
- original 83-session discovery window: 61 trades, 63.9% win, +15.71%,
  PF 1.92;
- latest 60 sessions: 45 trades, 64.4% win, +14.51%, PF 2.13.

This changes the interpretation. Both rules are profitable over the complete
sample only because their recent MRVL performance is strong. Neither rule
survived the earlier 168-session backcast. They are therefore
**MRVL recent-regime candidates**, not stable year-round MRVL rules.

The regime evidence is economically coherent:

- median 3-minute ATR rose from 0.22% in the earlier period to 0.32% in the
  discovery period and 0.36% in the latest 60 sessions;
- median daily range rose from 3.73% to 5.56%, reaching 6.53% in the latest
  60 sessions;
- median absolute daily open-to-close move rose from 1.39% to 2.42%;
- positive sessions increased from 47.0% to 61.4%;
- median prior 20-session return changed from about -1.0% to +31.3%.

The 2% target is much more reachable in this higher-volatility, positive-drift
state. The rules are detecting selloffs inside a strong active regime, where
temporary liquidity pressure is more likely to rebound. In quieter or
directionally weaker MRVL regimes, time exits and 10 bps costs consume the
small rebounds.

Primary remains first because it has the larger sample, tighter 0.8% stop,
higher total simulated return, and broader daily coverage. Secondary is a
more selective confirmation rule: it has higher recent win rate and PF but a
1.0% stop and fewer trades. It is not an independent diversifier. Of the raw
secondary signal bars, 82.5% also satisfy the primary rule; 56.4% of primary
signals satisfy the secondary rule. When both fire, the secondary should be
treated as a higher-confidence version of the same setup rather than a second
position.

No regime gate is promoted yet. A simple prior-day range split did not remove
the earlier losses, so volatility alone is insufficient. The next gate should
combine causal pre-entry information about MRVL's medium-term price regime and
current participation, then be frozen and tested forward.

### Frozen MRVL rules applied to other stocks

The exact MRVL parameters were applied to CRDO, AAOI, and RKLB over their same
83-session research windows. Nothing was recalibrated by ticker.

| Ticker | Frozen rule | Trades | Win | Net | PF | Positive 20-session blocks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| CRDO | Primary | 74 | 39.2% | -8.78% | 0.76 | 2/4 |
| CRDO | Secondary | 56 | 48.2% | -3.17% | 0.88 | 2/4 |
| AAOI | Primary | 100 | 33.0% | -6.02% | 0.89 | 1/4 |
| AAOI | Secondary | 74 | 41.9% | +3.70% | 1.09 | 2/4 |
| RKLB | Primary | 66 | 50.0% | -3.35% | 0.88 | 2/4 |
| RKLB | Secondary | 54 | 51.9% | -2.73% | 0.88 | 1/4 |

The transfer test rejects both rules as universal strategies. AAOI secondary
is marginally positive, but PF 1.09 and only 2/4 positive blocks are not enough
to treat it as executable. This does not invalidate MRVL-specific use; it
supports discovering and calibrating a separate mechanism for each stock.

### MRVL short watch: low-volume trend exhaustion

- EMA9/EMA21 spread `>= +0.35%`;
- current 20-bar volume ratio `<= 0.5247`;
- target 1.5%, stop 0.8%, maximum hold 8 bars;
- maximum 2 trades per day.

It produced 24 train trades at PF 1.76 and 14 test trades at 64.3% win, +4.59%,
and PF 2.03. All six time blocks were positive, but the training sample is
below the 30-trade candidate gate. It remains `Watch`; actual short borrow or
an inverse execution instrument must be identified before paper validation.

## 15. Next Development Sequence

1. Make feature generation and turning-zone labeling reusable.
2. Persist strategy research runs and their exact assumptions.
3. Add transparent rule mining with walk-forward scoring.
4. Register qualified candidates in the strategy selector.
5. Re-run the same rule on additional history and neighboring thresholds.
6. Compare strategies on identical date ranges and execution assumptions.
7. Keep only candidates that remain coherent statistically and financially.

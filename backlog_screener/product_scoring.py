from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


MODEL_VERSION = "hidden_champion_v3"


@dataclass(frozen=True)
class HiddenChampionScore:
    ticker: str
    total_score: float
    grade: str
    component_scores: dict[str, Any]
    explanation: str
    missing_dimensions: list[str]


def score_hidden_champion(ticker: str, items: list[dict[str, Any]]) -> HiddenChampionScore:
    evidence = _latest_metrics(items)
    missing = _missing_dimensions(evidence)

    eligibility = _eligibility_score(evidence)
    valuation = _valuation_score(evidence)
    growth_quality = _growth_quality_score(evidence)
    order_quality = _order_quality_score(evidence)
    ownership_alignment = _ownership_alignment_score(evidence)
    financial_quality = _financial_quality_score(evidence)
    attention_flow = _attention_flow_score(evidence)
    information_quality = _information_quality_score(items)

    gross = (
        eligibility
        + valuation
        + growth_quality
        + order_quality
        + ownership_alignment
        + financial_quality
        + attention_flow
        + information_quality
    )
    total = max(0, min(100, gross - _missing_penalty(missing)))
    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 45 else "D"

    components = {
        "eligibility": round(eligibility, 2),
        "valuation": round(valuation, 2),
        "growth_quality": round(growth_quality, 2),
        "order_quality": round(order_quality, 2),
        "ownership_alignment": round(ownership_alignment, 2),
        "financial_quality": round(financial_quality, 2),
        "attention_flow": round(attention_flow, 2),
        "information_quality": round(information_quality, 2),
        # Compatibility keys for older UI/API consumers.
        "size": round(eligibility, 2),
        "growth": round(growth_quality, 2),
        "ownership": round(ownership_alignment, 2),
        "backlog_rpo": round(order_quality, 2),
        "raw_metrics": _raw_metrics(evidence, items),
    }
    explanation = _explain(ticker, total, components, missing)
    return HiddenChampionScore(
        ticker=ticker.upper(),
        total_score=round(total, 2),
        grade=grade,
        component_scores=components,
        explanation=explanation,
        missing_dimensions=missing,
    )


def _latest_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    seen_keys: set[str] = set()
    for item in sorted(items, key=lambda row: str(row.get("created_at") or ""), reverse=True):
        evidence = item.get("evidence") or {}
        for key, value in evidence.items():
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if value is not None:
                metrics[key] = value
    return metrics


def _eligibility_score(evidence: dict[str, Any]) -> float:
    market_cap = _num(evidence.get("market_cap"))
    if market_cap is None:
        return 0
    if 500_000_000 <= market_cap <= 4_000_000_000:
        return 14
    if 300_000_000 <= market_cap < 500_000_000:
        return 9
    if 4_000_000_000 < market_cap <= 8_000_000_000:
        return 7
    if 8_000_000_000 < market_cap <= 15_000_000_000:
        return 3
    return 1


def _valuation_score(evidence: dict[str, Any]) -> float:
    pe = _num(evidence.get("pe_ttm"))
    if pe is None:
        return 0
    if 0 < pe <= 20:
        return 12
    if 20 < pe <= 30:
        return 9
    if 30 < pe <= 45:
        return 4
    return 0


def _growth_quality_score(evidence: dict[str, Any]) -> float:
    revenue_yoy = _num(evidence.get("quarterly_revenue_yoy"))
    score = 0.0
    if revenue_yoy is not None:
        if revenue_yoy >= 0.5:
            score += 16
        elif revenue_yoy >= 0.25:
            score += 13
        elif revenue_yoy >= 0.1:
            score += 7
    receivables_yoy = _num(evidence.get("receivables_yoy"))
    inventory_yoy = _num(evidence.get("inventory_yoy"))
    if revenue_yoy is not None and receivables_yoy is not None:
        score += 3 if receivables_yoy <= revenue_yoy + 0.15 else -2
    if revenue_yoy is not None and inventory_yoy is not None:
        score += 2 if inventory_yoy <= revenue_yoy + 0.2 else -2
    return max(0, min(20, score))


def _order_quality_score(evidence: dict[str, Any]) -> float:
    backlog_mentions = _num(evidence.get("backlog_mentions")) or 0
    rpo_mentions = _num(evidence.get("rpo_mentions")) or 0
    largest_amount = _num(evidence.get("backlog_largest_amount") or evidence.get("largest_amount"))
    revenue = _num(evidence.get("revenue"))
    gov_award_count = _num(evidence.get("government_contract_award_count")) or 0
    gov_total_value = _num(evidence.get("government_contract_total_value"))
    gov_dod_value = _num(evidence.get("government_contract_dod_value"))
    signal = backlog_mentions + rpo_mentions
    score = 0.0
    if signal >= 20:
        score += 9
    elif signal >= 8:
        score += 7
    elif signal >= 1:
        score += 4
    if rpo_mentions > 0:
        score += 3
    if largest_amount is not None:
        score += 4
        if revenue:
            ratio = largest_amount / revenue
            if ratio >= 2:
                score += 4
            elif ratio >= 1:
                score += 2
    if gov_award_count >= 1:
        score += 2
    if gov_total_value is not None:
        if gov_total_value >= 100_000_000:
            score += 4
        elif gov_total_value >= 25_000_000:
            score += 3
        elif gov_total_value >= 5_000_000:
            score += 1
    if gov_dod_value is not None and gov_dod_value >= 10_000_000:
        score += 1
    return min(20, score)


def _ownership_alignment_score(evidence: dict[str, Any]) -> float:
    insider = _num(evidence.get("insider_ownership") or evidence.get("proxy_management_ownership"))
    institutional = _num(evidence.get("institutional_ownership"))
    large_holder = _num(evidence.get("large_holder_max_percent") or evidence.get("proxy_top_holder_percent"))
    insider_net = _num(evidence.get("insider_net_purchase_value"))
    institution_count = _num(evidence.get("institutional_13f_manager_count"))
    score = 0.0
    if insider is not None:
        score += 6 if insider >= 0.05 else 3 if insider >= 0.02 else 1
    if institutional is not None:
        score += 4 if institutional >= 0.65 else 2 if institutional >= 0.4 else 0
    if large_holder is not None:
        score += 3 if large_holder >= 0.1 else 2 if large_holder >= 0.05 else 0
    if insider_net is not None:
        score += 3 if insider_net > 0 else -2 if insider_net < -2_000_000 else 0
    if institution_count is not None:
        score += min(2, institution_count)
    return max(0, min(14, score))


def _financial_quality_score(evidence: dict[str, Any]) -> float:
    score = 0.0
    gross_margin = _num(evidence.get("gross_margin"))
    operating_margin = _num(evidence.get("operating_margin"))
    net_margin = _num(evidence.get("net_margin"))
    fcf_margin = _num(evidence.get("free_cash_flow_margin"))
    liabilities_to_assets = _num(evidence.get("liabilities_to_assets"))
    debt_to_assets = _num(evidence.get("debt_to_assets"))
    if gross_margin is not None:
        score += 4 if gross_margin >= 0.35 else 2 if gross_margin >= 0.2 else 0
    if operating_margin is not None:
        score += 4 if operating_margin >= 0.15 else 2 if operating_margin >= 0.08 else 0
    if net_margin is not None:
        score += 3 if net_margin >= 0.1 else 1 if net_margin > 0 else -2
    if fcf_margin is not None:
        score += 3 if fcf_margin >= 0.08 else 1 if fcf_margin >= 0 else -2
    if liabilities_to_assets is not None:
        score += 2 if liabilities_to_assets <= 0.55 else -1 if liabilities_to_assets > 0.75 else 0
    if debt_to_assets is not None:
        score += 2 if debt_to_assets <= 0.25 else -1 if debt_to_assets > 0.5 else 0
    return max(0, min(16, score))


def _attention_flow_score(evidence: dict[str, Any]) -> float:
    large_ratio = _num(evidence.get("large_buy_sell_ratio"))
    large_net_flow = _num(evidence.get("large_net_flow_20d"))
    return_20d = _num(evidence.get("return_20d"))
    label = str(evidence.get("attention_flow_label") or "")
    if large_ratio is None and large_net_flow is None and return_20d is None:
        return 0

    score = 0.0
    ratio_buy_pressure = False
    net_flow_buy_pressure = False
    if large_ratio is not None:
        if large_ratio >= 1.8:
            score += 4
            ratio_buy_pressure = True
        elif large_ratio >= 1.3:
            score += 3
            ratio_buy_pressure = True
        elif large_ratio >= 1.05:
            score += 1
            ratio_buy_pressure = True
        elif large_ratio < 0.8:
            score -= 2
    if large_net_flow is not None:
        if large_net_flow > 0:
            score += 1
            net_flow_buy_pressure = True
        elif large_net_flow < 0:
            score -= 1
    has_buy_pressure = ratio_buy_pressure or (large_ratio is None and net_flow_buy_pressure)
    if return_20d is not None:
        if has_buy_pressure and -0.08 <= return_20d <= 0.12:
            score += 3
        elif has_buy_pressure and return_20d <= 0.20:
            score += 1
        elif return_20d >= 0.45:
            score -= 7
        elif return_20d >= 0.30:
            score -= 5
        elif return_20d >= 0.20:
            score -= 3
        elif return_20d < -0.20:
            score -= 1
    if label == "quiet_accumulation":
        score += 1
    elif label == "crowded_momentum":
        score -= 2
    elif label == "distribution_risk":
        score -= 2
    return max(-8, min(8, score))


def _information_quality_score(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0
    source_count = len({item.get("source_key") for item in items if item.get("source_key")})
    top_importance = max(float(item.get("importance_score") or 0) for item in items)
    return min(8, source_count * 1.2) + min(4, top_importance / 25)


def _missing_dimensions(evidence: dict[str, Any]) -> list[str]:
    missing = []
    if evidence.get("market_cap") is None:
        missing.append("market_cap")
    if evidence.get("pe_ttm") is None:
        missing.append("pe_ttm")
    if evidence.get("quarterly_revenue_yoy") is None:
        missing.append("quarterly_revenue_yoy")
    if evidence.get("gross_margin") is None and evidence.get("operating_margin") is None:
        missing.append("financial_quality")
    if not (evidence.get("backlog_mentions") or evidence.get("rpo_mentions")):
        missing.append("backlog_or_rpo")
    if evidence.get("insider_ownership") is None and evidence.get("proxy_management_ownership") is None:
        missing.append("insider_ownership")
    if (
        evidence.get("institutional_ownership") is None
        and evidence.get("institutional_13f_manager_count") is None
        and evidence.get("large_holder_max_percent") is None
    ):
        missing.append("institutional_holder_signal")
    return missing


def _missing_penalty(missing: list[str]) -> float:
    penalty_map = {
        "market_cap": 5,
        "pe_ttm": 3,
        "quarterly_revenue_yoy": 6,
        "financial_quality": 4,
        "backlog_or_rpo": 8,
        "insider_ownership": 3,
        "institutional_holder_signal": 2,
    }
    return sum(penalty_map.get(item, 1) for item in missing)


def _raw_metrics(evidence: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "market_cap": evidence.get("market_cap"),
        "pe_ttm": evidence.get("pe_ttm"),
        "quarterly_revenue_yoy": evidence.get("quarterly_revenue_yoy"),
        "backlog_mentions": evidence.get("backlog_mentions") or 0,
        "rpo_mentions": evidence.get("rpo_mentions") or 0,
        "backlog_largest_amount": evidence.get("backlog_largest_amount") or evidence.get("largest_amount"),
        "gross_margin": evidence.get("gross_margin"),
        "operating_margin": evidence.get("operating_margin"),
        "net_margin": evidence.get("net_margin"),
        "free_cash_flow_margin": evidence.get("free_cash_flow_margin"),
        "debt_to_assets": evidence.get("debt_to_assets"),
        "receivables_yoy": evidence.get("receivables_yoy"),
        "inventory_yoy": evidence.get("inventory_yoy"),
        "insider_ownership": evidence.get("insider_ownership") or evidence.get("proxy_management_ownership"),
        "institutional_ownership": evidence.get("institutional_ownership"),
        "large_holder_max_percent": evidence.get("large_holder_max_percent"),
        "insider_net_purchase_value": evidence.get("insider_net_purchase_value"),
        "institutional_13f_manager_count": evidence.get("institutional_13f_manager_count"),
        "large_buy_sell_ratio": evidence.get("large_buy_sell_ratio"),
        "super_buy_sell_ratio": evidence.get("super_buy_sell_ratio"),
        "large_net_flow_20d": evidence.get("large_net_flow_20d"),
        "return_5d": evidence.get("return_5d"),
        "return_20d": evidence.get("return_20d"),
        "return_60d": evidence.get("return_60d"),
        "attention_flow_label": evidence.get("attention_flow_label"),
        "government_contract_award_count": evidence.get("government_contract_award_count"),
        "government_contract_total_value": evidence.get("government_contract_total_value"),
        "government_contract_largest_award": evidence.get("government_contract_largest_award"),
        "government_contract_dod_value": evidence.get("government_contract_dod_value"),
        "source_count": len({item.get("source_key") for item in items if item.get("source_key")}),
    }


def _explain(ticker: str, total: float, components: dict[str, Any], missing: list[str]) -> str:
    raw = components["raw_metrics"]
    parts = [f"{ticker.upper()} 隐形冠军候选分 {total:.1f}。"]
    if raw.get("market_cap") is not None:
        parts.append(f"市值约 {_money(raw['market_cap'])}。")
    if raw.get("quarterly_revenue_yoy") is not None:
        parts.append(f"季度营收同比约 {raw['quarterly_revenue_yoy'] * 100:.1f}%。")
    if raw.get("backlog_mentions") or raw.get("rpo_mentions"):
        parts.append(f"Backlog/RPO 文本线索 {raw.get('backlog_mentions', 0) + raw.get('rpo_mentions', 0)} 处。")
    if raw.get("government_contract_award_count"):
        parts.append(
            f"近年政府合同线索 {int(raw['government_contract_award_count'])} 项，"
            f"合计约 {_money(raw.get('government_contract_total_value') or 0)}。"
        )
    if raw.get("insider_ownership") is not None:
        parts.append(f"管理层/内部人持股约 {raw['insider_ownership'] * 100:.1f}%。")
    if raw.get("large_buy_sell_ratio") is not None and raw.get("return_20d") is not None:
        parts.append(
            f"主力大单买卖比约 {raw['large_buy_sell_ratio']:.2f}，"
            f"近20日涨幅约 {raw['return_20d'] * 100:.1f}%。"
        )
    if missing:
        parts.append("仍缺少：" + ", ".join(missing) + "。")
    return "".join(parts)


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"

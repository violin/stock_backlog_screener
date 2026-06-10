from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional, Protocol, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .settings import AppSettings


@dataclass(frozen=True)
class LlmSummary:
    summary: str
    importance_score: float
    sentiment_score: float
    confidence_score: float
    raw_response: str
    provider: str = "minimax"


@dataclass(frozen=True)
class CompanyProfileSummary:
    business: str
    industry_role: str
    recommendation_reason: list[str]
    risks: list[str]
    watch_items: list[str]
    confidence_score: float
    raw_response: str
    provider: str = "minimax"

    def to_dict(self) -> dict:
        return {
            "business": self.business,
            "industry_role": self.industry_role,
            "recommendation_reason": self.recommendation_reason,
            "risks": self.risks,
            "watch_items": self.watch_items,
            "confidence_score": self.confidence_score,
            "provider": self.provider,
        }


class SummaryClient(Protocol):
    def summarize_filing_signal(self, *, ticker: str, title: str, text: str) -> LlmSummary:
        ...

    def summarize_company_profile(
        self,
        *,
        ticker: str,
        company: dict,
        score: dict | None,
        items: list[dict],
    ) -> CompanyProfileSummary:
        ...

    def summarize_crawled_source(
        self,
        *,
        ticker: str,
        source_name: str,
        source_url: str,
        snippets: list[dict],
    ) -> LlmSummary:
        ...


class MiniMaxClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.minimaxi.com/anthropic/v1",
        model: str = "MiniMax-M2.7",
        api: str = "anthropic-messages",
        timeout: int = 45,
        retries: int = 1,
        retry_wait_seconds: float = 30,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api = api
        self.timeout = timeout
        self.retries = max(0, retries)
        self.retry_wait_seconds = max(0, retry_wait_seconds)

    def summarize_filing_signal(self, *, ticker: str, title: str, text: str) -> LlmSummary:
        system = (
            "你是美股中小盘产业链研究员。你的任务是从公司公告/财报片段中提炼"
            "和隐形冠军选股有关的可验证信息。只输出 JSON。"
        )
        payload = self._payload(system=system, user=_prompt(ticker=ticker, title=title, text=text))
        response = self._post_with_retry(payload)
        response.raise_for_status()
        data = response.json()
        content = _response_content(data)
        parsed = _extract_json(content)
        return LlmSummary(
            summary=str(parsed.get("summary") or "").strip() or content.strip(),
            importance_score=_score(parsed.get("importance_score"), default=65),
            sentiment_score=_score(parsed.get("sentiment_score"), default=0),
            confidence_score=_score(parsed.get("confidence_score"), default=65),
            raw_response=content,
        )

    def summarize_company_profile(
        self,
        *,
        ticker: str,
        company: dict,
        score: dict | None,
        items: list[dict],
    ) -> CompanyProfileSummary:
        system = (
            "你是资深美股产业链研究员，擅长把结构化证据压缩成投研摘要。"
            "只依据输入事实，不编造业务、客户、订单或财务数据。只输出 JSON。"
        )
        payload = self._payload(
            system=system,
            user=_company_profile_prompt(
                ticker=ticker,
                company=company,
                score=score,
                items=items,
            ),
        )
        response = self._post_with_retry(payload)
        response.raise_for_status()
        data = response.json()
        content = _response_content(data)
        parsed = _extract_json(content)
        return CompanyProfileSummary(
            business=_text(parsed.get("business")),
            industry_role=_text(parsed.get("industry_role")),
            recommendation_reason=_string_list(parsed.get("recommendation_reason")),
            risks=_string_list(parsed.get("risks")),
            watch_items=_string_list(parsed.get("watch_items")),
            confidence_score=_score(parsed.get("confidence_score"), default=65),
            raw_response=content,
        )

    def summarize_crawled_source(
        self,
        *,
        ticker: str,
        source_name: str,
        source_url: str,
        snippets: list[dict],
    ) -> LlmSummary:
        system = (
            "你是投研工具里的网页抓取译审。你的任务是把英文官网/IR/新闻页面片段"
            "忠实翻译并压缩成中文说明。不要泛泛总结成关键词扫描结果，只表达原文实际意思。"
            "只输出 JSON。"
        )
        payload = self._payload(
            system=system,
            user=_crawled_source_prompt(
                ticker=ticker,
                source_name=source_name,
                source_url=source_url,
                snippets=snippets,
            ),
        )
        response = self._post_with_retry(payload)
        response.raise_for_status()
        data = response.json()
        content = _response_content(data)
        parsed = _extract_json(content)
        return LlmSummary(
            summary=_text(parsed.get("summary")) or content.strip(),
            importance_score=_score(parsed.get("importance_score"), default=68),
            sentiment_score=_score(parsed.get("sentiment_score"), default=0),
            confidence_score=_score(parsed.get("confidence_score"), default=62),
            raw_response=content,
        )

    def complete_json(self, *, system: str, user: str) -> dict:
        payload = self._payload(system=system, user=user)
        response = self._post_with_retry(payload)
        response.raise_for_status()
        content = _response_content(response.json())
        parsed = _extract_json(content)
        parsed["raw_response"] = content
        parsed["provider"] = "minimax"
        return parsed

    def _payload(self, *, system: str, user: str) -> dict:
        if self.api == "openai-completions":
            return {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            }
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{system}\n\n{user}",
                }
            ],
        }

    def _post_with_retry(self, payload: dict) -> requests.Response:
        if self.api == "openai-completions":
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            url = f"{self.base_url}/chat/completions"
        else:
            headers = {
                "X-Api-Key": self.api_key,
                "Content-Type": "application/json",
            }
            url = f"{self.base_url}/messages"
        last_response = None
        for attempt in range(self.retries + 1):
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 429 or attempt >= self.retries:
                return response
            last_response = response
            wait_seconds = _retry_after_seconds(response) or self.retry_wait_seconds * (attempt + 1)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
        return last_response


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model: str = "gemini-2.5-flash",
        timeout: int = 45,
        retries: int = 1,
        retry_wait_seconds: float = 30,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.retries = max(0, retries)
        self.retry_wait_seconds = max(0, retry_wait_seconds)

    def summarize_filing_signal(self, *, ticker: str, title: str, text: str) -> LlmSummary:
        system = (
            "你是美股中小盘产业链研究员。你的任务是从公司公告/财报片段中提炼"
            "和隐形冠军选股有关的可验证信息。只输出 JSON。"
        )
        payload = self._payload(system=system, user=_prompt(ticker=ticker, title=title, text=text))
        response = self._post_with_retry(payload)
        response.raise_for_status()
        data = response.json()
        content = _gemini_response_content(data)
        parsed = _extract_json(content)
        return LlmSummary(
            summary=str(parsed.get("summary") or "").strip() or content.strip(),
            importance_score=_score(parsed.get("importance_score"), default=65),
            sentiment_score=_score(parsed.get("sentiment_score"), default=0),
            confidence_score=_score(parsed.get("confidence_score"), default=65),
            raw_response=content,
            provider="gemini",
        )

    def summarize_company_profile(
        self,
        *,
        ticker: str,
        company: dict,
        score: dict | None,
        items: list[dict],
    ) -> CompanyProfileSummary:
        system = (
            "你是资深美股产业链研究员，擅长把结构化证据压缩成投研摘要。"
            "只依据输入事实，不编造业务、客户、订单或财务数据。只输出 JSON。"
        )
        payload = self._payload(
            system=system,
            user=_company_profile_prompt(
                ticker=ticker,
                company=company,
                score=score,
                items=items,
            ),
        )
        response = self._post_with_retry(payload)
        response.raise_for_status()
        data = response.json()
        content = _gemini_response_content(data)
        parsed = _extract_json(content)
        return CompanyProfileSummary(
            business=_text(parsed.get("business")),
            industry_role=_text(parsed.get("industry_role")),
            recommendation_reason=_string_list(parsed.get("recommendation_reason")),
            risks=_string_list(parsed.get("risks")),
            watch_items=_string_list(parsed.get("watch_items")),
            confidence_score=_score(parsed.get("confidence_score"), default=65),
            raw_response=content,
            provider="gemini",
        )

    def summarize_crawled_source(
        self,
        *,
        ticker: str,
        source_name: str,
        source_url: str,
        snippets: list[dict],
    ) -> LlmSummary:
        system = (
            "你是投研工具里的网页抓取译审。你的任务是把英文官网/IR/新闻页面片段"
            "忠实翻译并压缩成中文说明。不要泛泛总结成关键词扫描结果，只表达原文实际意思。"
            "只输出 JSON。"
        )
        payload = self._payload(
            system=system,
            user=_crawled_source_prompt(
                ticker=ticker,
                source_name=source_name,
                source_url=source_url,
                snippets=snippets,
            ),
        )
        response = self._post_with_retry(payload)
        response.raise_for_status()
        data = response.json()
        content = _gemini_response_content(data)
        parsed = _extract_json(content)
        return LlmSummary(
            summary=_text(parsed.get("summary")) or content.strip(),
            importance_score=_score(parsed.get("importance_score"), default=68),
            sentiment_score=_score(parsed.get("sentiment_score"), default=0),
            confidence_score=_score(parsed.get("confidence_score"), default=62),
            raw_response=content,
            provider="gemini",
        )

    def _payload(self, *, system: str, user: str) -> dict:
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system}\n\n{user}"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
            },
        }

    def _post_with_retry(self, payload: dict) -> requests.Response:
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        last_response = None
        for attempt in range(self.retries + 1):
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 429 or attempt >= self.retries:
                return response
            last_response = response
            wait_seconds = _retry_after_seconds(response) or self.retry_wait_seconds * (attempt + 1)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
        return last_response


def build_llm_client(settings: AppSettings) -> SummaryClient | None:
    provider = (settings.llm_provider or "minimax").strip().lower()
    if provider == "gemini":
        if not settings.gemini_api_key:
            return None
        return GeminiClient(
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            model=settings.gemini_model,
            retries=settings.gemini_retries,
            retry_wait_seconds=settings.gemini_retry_wait_seconds,
        )
    if not settings.minimax_api_key:
        return None
    return MiniMaxClient(
        api_key=settings.minimax_api_key,
        base_url=settings.minimax_base_url,
        model=settings.minimax_model,
        api=settings.minimax_api,
        retries=settings.minimax_retries,
        retry_wait_seconds=settings.minimax_retry_wait_seconds,
    )


def heuristic_summary(*, ticker: str, snippets: list[str], backlog_mentions: int, rpo_mentions: int) -> LlmSummary:
    signal = backlog_mentions + rpo_mentions
    if signal:
        summary = (
            f"{ticker} 最新 SEC 文件中出现 {backlog_mentions} 次 backlog 和 {rpo_mentions} 次 RPO/"
            "remaining performance obligations 线索，需要进一步判断订单增速、取消条款和毛利质量。"
        )
    else:
        summary = f"{ticker} 最新 SEC 文件未检出明确 Backlog/RPO 线索。"
    if snippets:
        summary += " 关键片段：" + snippets[0][:280]
    return LlmSummary(
        summary=summary,
        importance_score=min(95, 50 + signal * 3),
        sentiment_score=8 if signal else 0,
        confidence_score=72 if signal else 55,
        raw_response="",
        provider="heuristic",
    )


def _prompt(*, ticker: str, title: str, text: str) -> str:
    return f"""
请分析 {ticker} 的这段原始资料，标题：{title}

关注目标：寻找“隐形冠军”美股标的，尤其是订单积压、RPO、下游瓶颈、数据中心/电力/工业基础设施/航天供应链等可验证信号。

请输出 JSON，字段：
{{
  "summary": "中文，2-4 句，包含可验证事实和投资含义，不要编造",
  "importance_score": 0-100,
  "sentiment_score": -100 到 100,
  "confidence_score": 0-100
}}

原始文本：
{text[:9000]}
""".strip()


def _company_profile_prompt(*, ticker: str, company: dict, score: dict | None, items: list[dict]) -> str:
    context = {
        "ticker": ticker.upper(),
        "company": {
            "name": company.get("name"),
            "sector": company.get("sector"),
            "industry": company.get("industry"),
            "metadata": company.get("metadata"),
        },
        "latest_score": _compact_score(score),
        "evidence_items": [_compact_item(item) for item in items[:36]],
    }
    return f"""
请基于以下结构化资料，为 {ticker.upper()} 生成“隐形冠军候选”摘要。

输出必须是 JSON，字段如下：
{{
  "business": "中文，1-2 句：公司是干什么的，只说输入中能支持的事实",
  "industry_role": "中文，1-2 句：它在所属板块/产业链中的角色、上游/下游位置或可能受益的瓶颈",
  "recommendation_reason": ["3-5 条中文要点：为什么值得进入候选池，不要写具体买入价或目标价"],
  "risks": ["3-5 条中文风险：估值、订单可持续性、客户/周期/毛利/内部人交易/信息缺口等"],
  "watch_items": ["2-4 条中文后续跟踪点：下一步需要验证什么"],
  "confidence_score": 0-100
}}

要求：
- 不要编造未在资料中出现的产品、客户、订单、合同或竞争地位。
- “推荐”只表示推荐进入研究清单，不代表买入建议。
- 如果证据不足，要明确说“证据不足/仍需验证”，不要强行下结论。
- 使用简洁中文，适合放在投研工具的摘要窗口。

资料 JSON：
{json.dumps(context, ensure_ascii=False, default=str)[:16000]}
""".strip()


def _crawled_source_prompt(*, ticker: str, source_name: str, source_url: str, snippets: list[dict]) -> str:
    compact_snippets = [
        {
            "term": item.get("term"),
            "page_label": item.get("page_label"),
            "url": item.get("url"),
            "snippet": item.get("snippet"),
        }
        for item in snippets[:8]
    ]
    return f"""
请把 {ticker.upper()} 的官网/IR 抓取片段翻译并整理成中文。

来源：
- 名称：{source_name}
- URL：{source_url}

输出必须是 JSON：
{{
  "summary": "中文，2-4 句。必须忠实表达英文原文具体意思，保留产品名、平台名、型号、客户类型等英文专有名词；不要写成“检出若干关键词”这种元描述。",
  "importance_score": 0-100,
  "sentiment_score": -100 到 100,
  "confidence_score": 0-100
}}

要求：
- 不要编造原文没有出现的订单、合同、客户、日期、金额或催化剂。
- 如果片段主要是产品/新闻列表，就翻译它列出的产品、平台、应用场景或新闻主题。
- 保留英文专有名词，例如 ZeroFlap、AEC、PILOT、GPU-to-GPU、scale-up/scale-out。
- 中文要适合直接放进投研工具的 Timetable/Truth 卡片。

抓取片段 JSON：
{json.dumps(compact_snippets, ensure_ascii=False, default=str)[:9000]}
""".strip()


def _compact_score(score: dict | None) -> dict | None:
    if not score:
        return None
    return {
        "total_score": score.get("total_score"),
        "grade": score.get("grade"),
        "component_scores": score.get("component_scores"),
        "explanation": score.get("explanation"),
        "missing_dimensions": score.get("missing_dimensions"),
    }


def _compact_item(item: dict) -> dict:
    evidence = item.get("evidence") or {}
    return {
        "dimension": item.get("dimension"),
        "source_key": item.get("source_key"),
        "event_date": str(item.get("event_date") or item.get("created_at") or "")[:10],
        "title": item.get("title"),
        "summary": item.get("summary"),
        "importance_score": item.get("importance_score"),
        "confidence_score": item.get("confidence_score"),
        "evidence": _compact_evidence(evidence),
    }


def _compact_evidence(evidence: dict) -> dict:
    keep_keys = (
        "sector",
        "industry",
        "market_cap",
        "pe_ttm",
        "pb",
        "price",
        "quarterly_revenue_yoy",
        "backlog_mentions",
        "rpo_mentions",
        "backlog_largest_amount",
        "largest_amount",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "free_cash_flow_margin",
        "debt_to_assets",
        "receivables_yoy",
        "inventory_yoy",
        "insider_ownership",
        "proxy_management_ownership",
        "large_holder_max_percent",
        "proxy_top_holder_percent",
        "insider_net_purchase_value",
        "institutional_13f_manager_count",
        "institutional_13f_value_usd",
        "large_buy_sell_ratio",
        "super_buy_sell_ratio",
        "large_net_flow_20d",
        "return_5d",
        "return_20d",
        "return_60d",
        "attention_flow_label",
    )
    return {key: evidence.get(key) for key in keep_keys if key in evidence and evidence.get(key) is not None}


def _extract_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        content = content[start : end + 1]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"summary": content}


def _response_content(data: dict) -> str:
    choices = data.get("choices")
    if choices:
        return str(choices[0].get("message", {}).get("content") or "")
    content = data.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text") is not None:
                    parts.append(str(block["text"]))
                elif block.get("text") is not None:
                    parts.append(str(block["text"]))
            elif block is not None:
                parts.append(str(block))
        return "\n".join(parts)
    message = data.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return json.dumps(data, ensure_ascii=False)


def _gemini_response_content(data: dict) -> str:
    candidates = data.get("candidates")
    if isinstance(candidates, list) and candidates:
        content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
        if isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                text_parts = [
                    str(part.get("text"))
                    for part in parts
                    if isinstance(part, dict) and part.get("text") is not None
                ]
                if text_parts:
                    return "\n".join(text_parts)
    return json.dumps(data, ensure_ascii=False)


def _retry_after_seconds(response: requests.Response) -> Optional[float]:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        return None


def _score(value, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(-100, min(100, number))


def _text(value) -> str:
    return str(value or "").strip()


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []

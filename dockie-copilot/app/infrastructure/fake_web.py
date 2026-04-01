"""
Remote-first fake web search client.

Loads a local source registry, but always searches deployed remote site indexes
over HTTP so the backend behaves as if it is browsing real websites.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.responses import (
    FakeWebSearchPlanResponseSchema,
    FakeWebSearchResponseSchema,
    FakeWebSearchResultSchema,
    FakeWebSourceSchema,
)

settings = get_settings()
logger = get_logger(__name__)


@dataclass(frozen=True)
class FakeWebSource:
    id: str
    name: str
    base_url: str
    search_index_url: str
    source_class: str
    trust_level: str
    topics: tuple[str, ...]


class FakeWebRegistry:
    def __init__(self, registry_path: str | None = None) -> None:
        configured = registry_path or settings.fake_web_registry_path
        self._registry_path = (Path(__file__).resolve().parents[2] / configured).resolve()
        self._sources: list[FakeWebSource] | None = None
        self._routing: dict[str, list[str]] | None = None

    def load(self) -> tuple[list[FakeWebSource], dict[str, list[str]]]:
        if self._sources is not None and self._routing is not None:
            return self._sources, self._routing

        payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
        self._sources = [
            FakeWebSource(
                id=item["id"],
                name=item["name"],
                base_url=item["base_url"],
                search_index_url=item["search_index_url"],
                source_class=item["source_class"],
                trust_level=item["trust_level"],
                topics=tuple(item.get("topics", [])),
            )
            for item in payload.get("sources", [])
        ]
        self._routing = {
            key: [str(source_id) for source_id in value]
            for key, value in payload.get("search_routing", {}).items()
        }
        return self._sources, self._routing


class FakeWebClient:
    def __init__(self, registry: FakeWebRegistry | None = None) -> None:
        self._registry = registry or FakeWebRegistry()
        self._index_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}

    async def search(
        self,
        *,
        query: str,
        topics: list[str] | None = None,
        limit: int | None = None,
    ) -> FakeWebSearchResponseSchema:
        normalized_query = _normalize_query(query)
        requested_topics = [topic for topic in (topics or _infer_topics(normalized_query)) if topic]
        candidate_sources = _resolve_candidate_sources(self._registry, requested_topics)[
            : max(settings.fake_web_max_sources_per_query, 1)
        ]
        result_limit = limit or settings.fake_web_max_results
        logger.info(
            "fake_web_search_started",
            query=query,
            normalized_query=normalized_query,
            topics=requested_topics,
            candidate_source_count=len(candidate_sources),
        )

        search_results: list[FakeWebSearchResultSchema] = []
        source_rows = await self._fetch_candidate_indexes(candidate_sources)
        for source, index_rows in zip(candidate_sources, source_rows):
            for row in index_rows:
                scored = _score_article(normalized_query, requested_topics, source, row)
                if scored is None:
                    continue
                search_results.append(scored)

        deduped_results = _dedupe_results(search_results)
        ranked = sorted(
            deduped_results,
            key=lambda item: (-item.relevance_score, item.source_id, item.id, item.url),
        )
        top_results = ranked[:result_limit]
        logger.info(
            "fake_web_search_completed",
            query=query,
            normalized_query=normalized_query,
            topics=requested_topics,
            raw_result_count=len(search_results),
            deduped_result_count=len(deduped_results),
            returned_result_count=len(top_results),
        )

        return FakeWebSearchResponseSchema(
            query=query,
            normalized_query=normalized_query,
            topics=requested_topics,
            candidate_sources=[
                FakeWebSourceSchema(
                    id=source.id,
                    name=source.name,
                    base_url=source.base_url,
                    search_index_url=source.search_index_url,
                    source_class=source.source_class,
                    trust_level=source.trust_level,
                    match_reason=_source_match_reason(source, requested_topics),
                )
                for source in candidate_sources
            ],
            results=top_results,
            retrieved_at=datetime.now(timezone.utc),
        )

    async def plan(
        self,
        *,
        query: str,
        topics: list[str] | None = None,
    ) -> FakeWebSearchPlanResponseSchema:
        normalized_query = _normalize_query(query)
        requested_topics = [topic for topic in (topics or _infer_topics(normalized_query)) if topic]
        candidate_sources = _resolve_candidate_sources(self._registry, requested_topics)
        return FakeWebSearchPlanResponseSchema(
            query=query,
            normalized_query=normalized_query,
            topics=requested_topics,
            candidate_sources=[
                FakeWebSourceSchema(
                    id=source.id,
                    name=source.name,
                    base_url=source.base_url,
                    search_index_url=source.search_index_url,
                    source_class=source.source_class,
                    trust_level=source.trust_level,
                    match_reason=_source_match_reason(source, requested_topics),
                )
                for source in candidate_sources
            ],
            retrieved_at=datetime.now(timezone.utc),
        )

    async def _fetch_search_index(self, source: FakeWebSource) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        cached = self._index_cache.get(source.id)
        if cached and now - cached[0] < timedelta(seconds=settings.fake_web_fetch_ttl_seconds):
            return cached[1]

        headers = {"User-Agent": settings.source_http_user_agent}
        async with httpx.AsyncClient(timeout=settings.source_http_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(source.search_index_url, headers=headers)
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError(f"Search index for {source.id} did not return a list")

        normalized_rows = [row for row in rows if isinstance(row, dict)]
        self._index_cache[source.id] = (now, normalized_rows)
        logger.info("fake_web_index_fetched", source_id=source.id, article_count=len(normalized_rows))
        return normalized_rows

    async def _fetch_candidate_indexes(
        self,
        candidate_sources: list[FakeWebSource],
    ) -> list[list[dict[str, Any]]]:
        if not candidate_sources:
            return []

        semaphore = asyncio.Semaphore(max(settings.fake_web_max_parallel_fetches, 1))

        async def fetch_one(source: FakeWebSource) -> list[dict[str, Any]]:
            async with semaphore:
                try:
                    return await self._fetch_search_index(source)
                except Exception as exc:
                    logger.warning("fake_web_source_fetch_failed", source_id=source.id, error=str(exc))
                    return []

        return await asyncio.gather(*(fetch_one(source) for source in candidate_sources))


def _normalize_query(query: str) -> str:
    query = query.lower().strip()
    query = re.sub(r"[^a-z0-9\s/-]+", " ", query)
    query = re.sub(r"\s+", " ", query)
    return query


def _resolve_candidate_sources(registry: FakeWebRegistry, requested_topics: list[str]) -> list[FakeWebSource]:
    sources, routing = registry.load()
    source_map = {source.id: source for source in sources}
    if requested_topics:
        ordered: list[str] = []
        for topic in requested_topics:
            for source_id in routing.get(topic, []):
                if source_id not in ordered:
                    ordered.append(source_id)
        candidate_ids = ordered or [source.id for source in sources]
    else:
        candidate_ids = [source.id for source in sources]
    return [source_map[source_id] for source_id in candidate_ids if source_id in source_map]


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1]


def _infer_topics(normalized_query: str) -> list[str]:
    topic_rules = {
        "vessel_position": ["where", "position", "tracking", "ais", "moving", "vessel"],
        "vessel_schedule": ["schedule", "eta", "arrival", "departure", "voyage"],
        "vessel_swap": ["swap", "substitution", "changed vessel", "different vessel"],
        "port_congestion": ["congestion", "anchorage", "queue", "berth delay", "port delay"],
        "berth_allocation": ["berth", "allocated berth", "berthing"],
        "customs_process": ["customs", "process", "clearance", "nicis", "form m"],
        "paar": ["paar"],
        "fx_rate": ["fx", "usd", "ngn", "exchange rate", "cbn"],
        "weather": ["weather", "rain", "swell", "storm", "monsoon"],
        "sanctions": ["sanction", "ofac", "compliance"],
        "carrier_performance": ["reliable", "performance", "on-time", "late carrier"],
        "demurrage": ["demurrage", "free days", "storage grace", "storage charge"],
        "freight_rates": ["freight rate", "shipping cost", "rate"],
        "port_news": ["news", "announcement", "notice", "update"],
    }
    inferred: list[str] = []
    for topic, phrases in topic_rules.items():
        if any(phrase in normalized_query for phrase in phrases):
            inferred.append(topic)
    return inferred


def _score_article(
    normalized_query: str,
    requested_topics: list[str],
    source: FakeWebSource,
    row: dict[str, Any],
) -> FakeWebSearchResultSchema | None:
    title = str(row.get("title", ""))
    summary = str(row.get("summary", ""))
    body = str(row.get("body", ""))
    tags = [str(tag) for tag in row.get("tags", []) if isinstance(tag, str)]
    haystack = " ".join([title, summary, body, " ".join(tags)]).lower()

    tokens = _tokenize(normalized_query)
    if not tokens:
        return None

    score = 0.0
    matched_tokens: list[str] = []
    for token in tokens:
        if token in title.lower():
            score += 3.5
            matched_tokens.append(token)
        elif token in summary.lower():
            score += 2.4
            matched_tokens.append(token)
        elif token in " ".join(tags).lower():
            score += 2.0
            matched_tokens.append(token)
        elif token in haystack:
            score += 1.0
            matched_tokens.append(token)

    if requested_topics and any(topic in source.topics for topic in requested_topics):
        score += 1.5

    trust_bonus = {"high": 1.2, "medium": 0.6, "low": 0.2}.get(source.trust_level, 0.0)
    score += trust_bonus

    if score <= 0:
        return None

    snippet = _build_snippet(summary=summary, body=body, tokens=tokens)
    match_reason = _build_match_reason(matched_tokens, requested_topics, source)

    return FakeWebSearchResultSchema(
        id=str(row.get("id", "")),
        title=title,
        url=str(row.get("url", source.base_url)),
        source=str(row.get("source", source.name)),
        source_id=source.id,
        source_type=str(row.get("source_type", "article")),
        source_class=source.source_class,
        trust_level=source.trust_level,
        published=row.get("published"),
        updated=row.get("updated"),
        summary=summary,
        snippet=snippet,
        tags=tags,
        relevance_score=round(score, 2),
        match_reason=match_reason,
    )


def _build_snippet(*, summary: str, body: str, tokens: list[str]) -> str:
    if summary:
        return summary
    text = body.strip().replace("\n", " ")
    for token in tokens:
        idx = text.lower().find(token)
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(text), idx + 160)
            return text[start:end].strip()
    return text[:180].strip()


def _build_match_reason(matched_tokens: list[str], requested_topics: list[str], source: FakeWebSource) -> str:
    reasons: list[str] = []
    if matched_tokens:
        unique_tokens = ", ".join(dict.fromkeys(matched_tokens))
        reasons.append(f"matched query terms: {unique_tokens}")
    if requested_topics:
        reasons.append(f"routed via topics: {', '.join(requested_topics)}")
    reasons.append(f"source trust: {source.trust_level}")
    return "; ".join(reasons)


def _source_match_reason(source: FakeWebSource, requested_topics: list[str]) -> str:
    if not requested_topics:
        return "searched as part of the full fake web corpus"
    matched_topics = [topic for topic in requested_topics if topic in source.topics]
    if matched_topics:
        return f"selected for topics: {', '.join(matched_topics)}"
    return "selected by route fallback"


def _dedupe_results(results: list[FakeWebSearchResultSchema]) -> list[FakeWebSearchResultSchema]:
    deduped: dict[str, FakeWebSearchResultSchema] = {}
    for result in results:
        dedupe_key = _result_dedupe_key(result)
        existing = deduped.get(dedupe_key)
        if existing is None or result.relevance_score > existing.relevance_score:
            deduped[dedupe_key] = result
    return list(deduped.values())


def _result_dedupe_key(result: FakeWebSearchResultSchema) -> str:
    normalized_url = result.url.rstrip("/").lower()
    if normalized_url:
        return f"url::{normalized_url}"
    normalized_title = re.sub(r"[^a-z0-9]+", " ", result.title.lower()).strip()
    return f"title::{normalized_title}"

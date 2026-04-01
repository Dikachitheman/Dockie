from __future__ import annotations

from types import SimpleNamespace

from app.infrastructure.fake_web import FakeWebClient, FakeWebRegistry


def _registry() -> FakeWebRegistry:
    return FakeWebRegistry("../fake-websites/sources.json")


async def _stub_fetch(self, source):  # pragma: no cover - helper for monkeypatching
    raise NotImplementedError


async def test_fake_web_search_routes_and_ranks_results(monkeypatch):
    client = FakeWebClient(registry=_registry())

    async def fake_fetch(self, source):
        payloads = {
            "nigeria-port-watch": [
                {
                    "id": "npw-test-1",
                    "title": "Lagos Port Congestion Update",
                    "url": "https://fake-websites-84bc.vercel.app/news/lagos-port-congestion-update",
                    "published": "2026-03-30",
                    "updated": "2026-03-30",
                    "source": "Nigeria Port Watch",
                    "source_type": "port_news",
                    "tags": ["lagos", "congestion", "port"],
                    "summary": "Anchorage congestion remains elevated in Lagos.",
                    "body": "Tin Can and Apapa are both running above normal queue levels."
                }
            ],
            "apapa-tin-can-terminal": [
                {
                    "id": "att-test-1",
                    "title": "Tin Can Berth Update",
                    "url": "https://fake-websites.vercel.app/notices/tin-can-berth-update",
                    "published": "2026-03-30",
                    "updated": "2026-03-30",
                    "source": "Apapa Tin Can Terminal",
                    "source_type": "berth_notice",
                    "tags": ["berth", "tin-can"],
                    "summary": "Berth allocation remains constrained.",
                    "body": "Lagos congestion is still affecting ro-ro planning."
                }
            ],
        }
        return payloads.get(source.id, [])

    monkeypatch.setattr(FakeWebClient, "_fetch_search_index", fake_fetch)

    result = await client.search(query="Lagos port congestion update", limit=5)

    assert result.topics
    assert result.results
    assert result.results[0].source_id == "nigeria-port-watch"
    assert "matched query terms" in result.results[0].match_reason
    assert any(source.id == "nigeria-port-watch" for source in result.candidate_sources)


async def test_fake_web_search_dedupes_duplicate_urls(monkeypatch):
    client = FakeWebClient(registry=_registry())

    duplicate_url = "https://example.test/shared-story"

    async def fake_fetch(self, source):
        return [
            {
                "id": f"{source.id}-1",
                "title": "Shared Lagos Story",
                "url": duplicate_url,
                "published": "2026-03-30",
                "updated": "2026-03-30",
                "source": source.name,
                "source_type": "story",
                "tags": ["lagos", "update"],
                "summary": "A duplicated story carried by multiple sources.",
                "body": "This article is intentionally duplicated for dedupe testing."
            }
        ]

    monkeypatch.setattr(FakeWebClient, "_fetch_search_index", fake_fetch)

    result = await client.search(query="lagos update", limit=10)

    assert len(result.results) == 1
    assert result.results[0].url == duplicate_url


async def test_fake_web_search_tolerates_source_fetch_failure(monkeypatch):
    client = FakeWebClient(registry=_registry())

    async def fake_fetch(self, source):
        if source.id == "nigeria-port-watch":
            raise RuntimeError("temporary failure")
        return [
            {
                "id": f"{source.id}-1",
                "title": "Fallback customs process explainer",
                "url": f"{source.base_url}/guides/fallback-customs-process",
                "published": "2026-03-30",
                "updated": "2026-03-30",
                "source": source.name,
                "source_type": "guide",
                "tags": ["customs", "process"],
                "summary": "A valid remote result from another source.",
                "body": "This should still be returned even if one source fails."
            }
        ]

    monkeypatch.setattr(FakeWebClient, "_fetch_search_index", fake_fetch)

    result = await client.search(query="customs process", topics=["customs_process"], limit=5)

    assert result.results
    assert all(item.source_id != "nigeria-port-watch" for item in result.results)


async def test_fake_web_search_caps_source_fan_out_and_fetches_in_parallel(monkeypatch):
    client = FakeWebClient(registry=_registry())
    monkeypatch.setattr(
        "app.infrastructure.fake_web.settings",
        SimpleNamespace(
            fake_web_max_sources_per_query=2,
            fake_web_max_parallel_fetches=2,
            fake_web_max_results=5,
            fake_web_fetch_ttl_seconds=300,
            source_http_user_agent="DockieCopilot/Test",
            source_http_timeout_seconds=5,
        ),
    )

    started: list[str] = []

    async def fake_fetch(self, source):
        started.append(source.id)
        if len(started) == 1:
            await __import__("asyncio").sleep(0)
        return [
            {
                "id": f"{source.id}-1",
                "title": f"{source.name} congestion update",
                "url": f"{source.base_url}/stories/{source.id}",
                "published": "2026-03-30",
                "updated": "2026-03-30",
                "source": source.name,
                "source_type": "story",
                "tags": ["lagos", "congestion"],
                "summary": "Parallel search test.",
                "body": "Parallel search test body.",
            }
        ]

    monkeypatch.setattr(FakeWebClient, "_fetch_search_index", fake_fetch)

    result = await client.search(query="lagos congestion", topics=["port_congestion"], limit=5)

    assert len(result.candidate_sources) == 2
    assert started == [source.id for source in result.candidate_sources]
    assert len(result.results) <= 2

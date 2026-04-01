"""
CLI entry points.

Usage:
  python -m app.cli.commands ingest
  python -m app.cli.commands refresh
  python -m app.cli.commands live_refresh
  python -m app.cli.commands simulated_refresh [run_name]
  python -m app.cli.commands apply_scenario <scenario_name>
  python -m app.cli.commands create_standby_agent "<condition_text>" [action] [shipment_id] [interval_seconds] [user_id] [user_email]
  python -m app.cli.commands list_standby_agents [user_id]
  python -m app.cli.commands run_standby_agent <agent_id> [user_id]
  python -m app.cli.commands list_standby_runs <agent_id>
  python -m app.cli.commands list_notifications [user_id]
  python -m app.cli.commands import_live_carriers
  python -m app.cli.commands embed_backfill [batch_size]
  python -m app.cli.commands embed_rebuild [batch_size] [--all]
  python -m app.cli.commands health
  python -m app.cli.commands aisdiag
  python -m app.cli.commands standby_worker
  python -m app.cli.commands standby_worker_once
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def _get_sync_engine():
    """Create a synchronous engine for Alembic / CLI use."""
    from sqlalchemy import create_engine
    from app.core.config import get_settings
    settings = get_settings()
    return create_engine(settings.sync_database_url, echo=False)


def _get_schema_revisions() -> tuple[str | None, str]:
    """Return the current DB revision and repo migration head."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script.get_current_head()

    engine = _get_sync_engine()
    try:
        with engine.connect() as connection:
            current_revision = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()

    return current_revision, head_revision


def _require_current_schema() -> None:
    """
    Fail fast with an actionable message when migrations have not been applied.
    """
    current_revision, head_revision = _get_schema_revisions()
    if current_revision == head_revision:
        return

    current_display = current_revision or "uninitialized"
    raise SystemExit(
        "Database schema is out of date "
        f"(current: {current_display}, expected: {head_revision}). "
        "Run `alembic upgrade head` and retry."
    )


async def _get_async_session():
    from app.infrastructure.database import AsyncSessionFactory
    return AsyncSessionFactory()


def _argv_or_default(index: int, default: str | None = None) -> str | None:
    return sys.argv[index] if len(sys.argv) > index else default


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

async def _cmd_ingest() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.cache import invalidate_cache_prefix
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.ingest import run_full_ingest

    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("cli_ingest_start")
    async with AsyncSessionFactory() as session:
        await run_full_ingest(session)
    await invalidate_cache_prefix("shipments:list")
    await invalidate_cache_prefix("sources:")
    logger.info("cli_ingest_done")


# ---------------------------------------------------------------------------
# refresh — simulate a new data refresh cycle
# ---------------------------------------------------------------------------

async def _cmd_refresh() -> None:
    """
    Apply the fixture refresh dataset as a new refresh cycle.
    """
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.cache import invalidate_cache_prefix
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.ingest import ingest_resource_pack

    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("cli_refresh_start", resource_pack_path=settings.resource_pack_refresh_path)
    async with AsyncSessionFactory() as session:
        counters = await ingest_resource_pack(session, Path(settings.resource_pack_refresh_path))
        await session.commit()

    logger.info("cli_refresh_done", counters=counters)
    await invalidate_cache_prefix("shipments:list")
    await invalidate_cache_prefix("sources:")
    print("Applied refresh resource pack:")
    for key, value in counters.items():
        print(f"  {key}={value}")


# ---------------------------------------------------------------------------
# live_refresh - refresh live/source connectors with source health updates
# ---------------------------------------------------------------------------

async def _cmd_live_refresh() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.cache import invalidate_cache_prefix
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.sources import refresh_sources

    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("cli_live_refresh_start")
    async with AsyncSessionFactory() as session:
        results = await refresh_sources(session)
        await session.commit()

    await invalidate_cache_prefix("shipments:")
    await invalidate_cache_prefix("sources:")
    logger.info(
        "cli_live_refresh_done",
        results=[
            {
                "source": item.source,
                "status": item.status,
                "attempted": item.attempted,
                "records_ingested": item.records_ingested,
            }
            for item in results
        ],
    )
    print("Refreshed configured source connectors:")
    for item in results:
        print(
            f"  {item.source}: status={item.status} attempted={item.attempted} "
            f"records_ingested={item.records_ingested}"
        )
        print(f"    {item.detail}")


# ---------------------------------------------------------------------------
# import_live_carriers - create stable shipments from live carrier pages
# ---------------------------------------------------------------------------

async def _cmd_import_live_carriers() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.database import AsyncSessionFactory
    from app.application.services import ShipmentService

    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("cli_import_live_carriers_start")
    async with AsyncSessionFactory() as session:
        svc = ShipmentService(session)
        created = await svc.import_live_carrier_shipments()

    print("Imported live carrier-backed shipments:")
    for item in created:
        vessel = item.candidate_vessels[0].name if item.candidate_vessels else "unknown vessel"
        print(f"  - {item.id} :: {item.carrier} :: {vessel} -> {item.discharge_port or 'unknown port'}")
    if not created:
        print("  (none found; run refresh first and confirm carrier schedule rows were parsed)")
    logger.info("cli_import_live_carriers_done", created_count=len(created))


# ---------------------------------------------------------------------------
# embed_backfill - generate embeddings for already ingested document chunks
# ---------------------------------------------------------------------------

async def _cmd_embed_backfill() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.embeddings import backfill_document_chunk_embeddings

    settings = get_settings()
    configure_logging(settings.log_level)

    batch_size = int(_argv_or_default(2, "100") or "100")
    total_embedded = 0

    async with AsyncSessionFactory() as session:
        while True:
            embedded = await backfill_document_chunk_embeddings(session, batch_size=batch_size)
            if embedded == 0:
                break
            total_embedded += embedded
            await session.commit()

    print(f"Embedded {total_embedded} document chunks.")


async def _cmd_embed_rebuild() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.embeddings import backfill_document_chunk_embeddings

    settings = get_settings()
    configure_logging(settings.log_level)

    batch_size = int(_argv_or_default(2, "100") or "100")
    full_rebuild = "--all" in sys.argv
    total_embedded = 0

    async with AsyncSessionFactory() as session:
        while True:
            embedded = await backfill_document_chunk_embeddings(
                session,
                batch_size=batch_size,
                stale_only=not full_rebuild,
            )
            if embedded == 0:
                break
            total_embedded += embedded
            await session.commit()

    mode = "all chunks" if full_rebuild else "stale chunks"
    print(f"Re-embedded {total_embedded} {mode}.")


# ---------------------------------------------------------------------------
# simulated_refresh - apply a fake position snapshot manually
# ---------------------------------------------------------------------------

async def _cmd_simulated_refresh() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.simulated_ingest import ingest_position_snapshot, simulated_root
    from app.infrastructure.cache import invalidate_cache_prefix

    settings = get_settings()
    configure_logging(settings.log_level)

    run_name = sys.argv[2] if len(sys.argv) > 2 else "run_002"
    snapshot_path = simulated_root() / "position_snapshots" / f"{run_name}.json"

    async with AsyncSessionFactory() as session:
        await ingest_position_snapshot(session, snapshot_path)
        await session.commit()

    await invalidate_cache_prefix("shipments:")
    print(f"Applied simulated position snapshot: {snapshot_path.name}")


# ---------------------------------------------------------------------------
# apply_scenario - apply a named fake business scenario manually
# ---------------------------------------------------------------------------

async def _cmd_apply_scenario() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.simulated_ingest import apply_simulated_scenario

    settings = get_settings()
    configure_logging(settings.log_level)

    if len(sys.argv) < 3:
        raise SystemExit("Usage: python -m app.cli.commands apply_scenario <scenario_name>")

    scenario_name = sys.argv[2]
    async with AsyncSessionFactory() as session:
        await apply_simulated_scenario(session, scenario_name)

    print(f"Applied simulated scenario: {scenario_name}")


# ---------------------------------------------------------------------------
# create_standby_agent - create a watcher quickly from the CLI
# ---------------------------------------------------------------------------

async def _cmd_create_standby_agent() -> None:
    from app.application.standby_services import StandbyAgentService
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.schemas.requests import StandbyAgentCreateRequest

    settings = get_settings()
    configure_logging(settings.log_level)

    if len(sys.argv) < 3:
        raise SystemExit(
            "Usage: python -m app.cli.commands create_standby_agent "
            "\"<condition_text>\" [action] [shipment_id] [interval_seconds] [user_id] [user_email]"
        )

    condition_text = sys.argv[2]
    action = _argv_or_default(3, "notify") or "notify"
    shipment_id = _argv_or_default(4)
    interval_seconds = int(_argv_or_default(5, "10") or "10")
    user_id = _argv_or_default(6, settings.adk_user_id) or settings.adk_user_id
    user_email = _argv_or_default(7)

    async with await _get_async_session() as session:
        svc = StandbyAgentService(session)
        agent = await svc.create_agent(
            user_id=user_id,
            user_email=user_email,
            payload=StandbyAgentCreateRequest(
                condition_text=condition_text,
                action=action,
                shipment_id=shipment_id,
                interval_seconds=interval_seconds,
            ),
        )

    print("Created standby agent:")
    print(f"  id={agent.id}")
    print(f"  trigger_type={agent.trigger_type}")
    print(f"  action={agent.action}")
    print(f"  shipment_id={agent.shipment_id or 'all-active-shipments'}")
    print(f"  next_run_at={agent.next_run_at}")


# ---------------------------------------------------------------------------
# list_standby_agents - inspect created watchers from the CLI
# ---------------------------------------------------------------------------

async def _cmd_list_standby_agents() -> None:
    from app.application.standby_services import StandbyAgentService
    from app.core.config import get_settings
    from app.core.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level)

    user_id = _argv_or_default(2, settings.adk_user_id) or settings.adk_user_id

    async with await _get_async_session() as session:
        svc = StandbyAgentService(session)
        agents = await svc.list_agents(user_id=user_id)

    if not agents:
        print(f"No standby agents found for user {user_id}.")
        return

    print(f"Standby agents for user {user_id}:")
    for agent in agents:
        print(
            "  - "
            f"{agent.id} :: {agent.trigger_type} :: {agent.action} :: "
            f"status={agent.status} :: shipment={agent.shipment_id or 'all'} :: "
            f"fire_count={agent.fire_count} :: last_result={agent.last_result or 'n/a'}"
        )


# ---------------------------------------------------------------------------
# run_standby_agent - force one evaluation for a specific watcher
# ---------------------------------------------------------------------------

async def _cmd_run_standby_agent() -> None:
    from app.application.standby_services import StandbyAgentService
    from app.core.config import get_settings
    from app.core.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level)

    if len(sys.argv) < 3:
        raise SystemExit("Usage: python -m app.cli.commands run_standby_agent <agent_id> [user_id]")

    agent_id = sys.argv[2]
    user_id = _argv_or_default(3, settings.adk_user_id) or settings.adk_user_id

    async with await _get_async_session() as session:
        svc = StandbyAgentService(session)
        agent = await svc.run_agent_now(user_id=user_id, agent_id=agent_id)

    if agent is None:
        print(f"Standby agent {agent_id} not found for user {user_id}.")
        return

    print("Ran standby agent:")
    print(f"  id={agent.id}")
    print(f"  status={agent.status}")
    print(f"  fire_count={agent.fire_count}")
    print(f"  last_result={agent.last_result}")
    print(f"  last_fired_at={agent.last_fired_at}")


# ---------------------------------------------------------------------------
# list_standby_runs - inspect evaluation history for a watcher
# ---------------------------------------------------------------------------

async def _cmd_list_standby_runs() -> None:
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.models.orm import StandbyAgentRun
    from sqlalchemy import select

    settings = get_settings()
    configure_logging(settings.log_level)

    if len(sys.argv) < 3:
        raise SystemExit("Usage: python -m app.cli.commands list_standby_runs <agent_id>")

    agent_id = sys.argv[2]

    async with await _get_async_session() as session:
        result = await session.execute(
            select(StandbyAgentRun)
            .where(StandbyAgentRun.agent_id == agent_id)
            .order_by(StandbyAgentRun.started_at.desc())
            .limit(50)
        )
        runs = result.scalars().all()

    if not runs:
        print(f"No standby runs found for agent {agent_id}.")
        return

    print(f"Standby runs for agent {agent_id}:")
    for run in runs:
        print(
            "  - "
            f"{run.started_at} :: matched={run.matched} :: action={run.action_executed or 'none'} :: "
            f"{run.result_text or 'n/a'}"
        )


# ---------------------------------------------------------------------------
# list_notifications - inspect watcher results from the CLI
# ---------------------------------------------------------------------------

async def _cmd_list_notifications() -> None:
    from app.application.standby_services import StandbyAgentService
    from app.core.config import get_settings
    from app.core.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level)

    user_id = _argv_or_default(2, settings.adk_user_id) or settings.adk_user_id

    async with await _get_async_session() as session:
        svc = StandbyAgentService(session)
        notifications = await svc.list_notifications(user_id=user_id)

    if not notifications:
        print(f"No notifications found for user {user_id}.")
        return

    print(f"Notifications for user {user_id}:")
    for item in notifications:
        print(
            "  - "
            f"{item.created_at} :: unread={item.unread} :: channel={item.channel} :: "
            f"{item.title} :: {item.detail}"
        )


# ---------------------------------------------------------------------------
# health — print source health table
# ---------------------------------------------------------------------------

async def _cmd_health() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.database import AsyncSessionFactory
    from app.infrastructure.repositories import SourceHealthRepository
    from app.domain.logic import is_stale

    settings = get_settings()
    configure_logging(settings.log_level)

    async with AsyncSessionFactory() as session:
        repo = SourceHealthRepository(session)
        rows = await repo.get_all()

    if not rows:
        print("No source health records found. Run 'ingest' first.")
        return

    now = datetime.now(timezone.utc)
    print(f"\n{'SOURCE':<30} {'CLASS':<35} {'STATUS':<12} {'STALE?':<8} {'LAST SUCCESS'}")
    print("-" * 110)
    for r in rows:
        stale = "YES" if (
            r.last_success_at and is_stale(r.last_success_at, r.stale_after_seconds, now=now)
        ) else "no"
        last = r.last_success_at.strftime("%Y-%m-%d %H:%M") if r.last_success_at else "never"
        print(f"{r.source:<30} {r.source_class:<35} {r.source_status:<12} {stale:<8} {last}")
    print()


# ---------------------------------------------------------------------------
# aisdiag - sample any active AIS messages
# ---------------------------------------------------------------------------

async def _cmd_aisdiag() -> None:
    from app.core.logging import configure_logging
    from app.core.config import get_settings
    from app.infrastructure.aisstream import capture_diagnostic_sample

    settings = get_settings()
    configure_logging(settings.log_level)

    if not settings.aisstream_api_key:
        raise SystemExit("AISSTREAM_API_KEY is not configured.")

    result = await capture_diagnostic_sample(api_key=settings.aisstream_api_key, sample_size=10)
    print(f"\nAIS diagnostic mode: {result.subscribed_mode}")
    print(f"Inspected messages: {result.inspected_messages}")
    print(f"Unique vessel samples: {len(result.sample)}")
    print(f"Message types seen: {', '.join(result.message_types) if result.message_types else 'none'}")
    if not result.sample:
        if result.raw_samples:
            print("\nRaw sample envelopes:")
            for idx, raw in enumerate(result.raw_samples, start=1):
                print(f"\n[{idx}] message_type={raw['message_type']}")
                print(f"keys={raw['keys']}")
                print(f"metadata_keys={raw['metadata_keys']}")
                print(f"message_keys={raw['message_keys']}")
                print(json.dumps(raw["payload"], indent=2)[:4000])
        else:
            print("No live AIS messages captured in the current window.\n")
        print()
        return

    print(f"\n{'MMSI':<12} {'VESSEL':<28} {'IMO':<12} {'OBSERVED AT':<26} {'DESTINATION'}")
    print("-" * 100)
    for item in result.sample:
        vessel_name = str(item.get("vessel_name") or "")[:27]
        imo = str(item.get("imo") or "")
        observed_at = str(item.get("observed_at") or "")
        destination = str(item.get("destination_text") or "")
        print(f"{item['mmsi']:<12} {vessel_name:<28} {imo:<12} {observed_at:<26} {destination}")
    print()


# ---------------------------------------------------------------------------
# standby_worker - evaluate due standby agents continuously
# ---------------------------------------------------------------------------

async def _cmd_standby_worker(run_once: bool = False) -> None:
    from app.application.standby_services import StandbyAgentService
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.infrastructure.database import AsyncSessionFactory

    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info(
        "standby_worker_start",
        poll_seconds=settings.standby_worker_poll_seconds,
        batch_size=settings.standby_worker_batch_size,
        run_once=run_once,
    )

    while True:
        async with AsyncSessionFactory() as session:
            svc = StandbyAgentService(session)
            processed = await svc.process_due_agents(limit=settings.standby_worker_batch_size)
            digests = await svc.process_due_digests(limit=settings.standby_worker_batch_size)

        if run_once:
            print(f"Processed {processed} standby agents and {digests} digest items.")
            return

        await asyncio.sleep(settings.standby_worker_poll_seconds)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

COMMANDS = {
    "ingest": _cmd_ingest,
    "refresh": _cmd_refresh,
    "live_refresh": _cmd_live_refresh,
    "simulated_refresh": _cmd_simulated_refresh,
    "apply_scenario": _cmd_apply_scenario,
    "create_standby_agent": _cmd_create_standby_agent,
    "list_standby_agents": _cmd_list_standby_agents,
    "run_standby_agent": _cmd_run_standby_agent,
    "list_standby_runs": _cmd_list_standby_runs,
    "list_notifications": _cmd_list_notifications,
    "import_live_carriers": _cmd_import_live_carriers,
    "embed_backfill": _cmd_embed_backfill,
    "embed_rebuild": _cmd_embed_rebuild,
    "health": _cmd_health,
    "aisdiag": _cmd_aisdiag,
    "standby_worker": _cmd_standby_worker,
    "standby_worker_once": lambda: _cmd_standby_worker(run_once=True),
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python -m app.cli.commands [{' | '.join(COMMANDS)}]")
        sys.exit(1)

    cmd = sys.argv[1]
    _require_current_schema()
    asyncio.run(COMMANDS[cmd]())


if __name__ == "__main__":
    main()

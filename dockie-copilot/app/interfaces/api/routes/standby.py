from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
import asyncio
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.standby_services import StandbyAgentService
from app.core.logging import get_logger
from app.infrastructure.database import get_db
from app.interfaces.api.user_context import RequestUserContext, get_request_user_context
from app.schemas.requests import (
    NotificationReadRequest,
    StandbyAgentCreateRequest,
    StandbyAgentUpdateRequest,
)
from app.schemas.responses import AgentOutputSchema, StandbyAgentSchema, UserNotificationSchema

router = APIRouter(tags=["standby"])
logger = get_logger(__name__)


@router.post("/standby-worker/start")
async def start_standby_worker(request: Request):
    app = request.app
    # Prevent multiple workers from being started
    existing = getattr(app.state, "standby_worker_task", None)
    if existing and not existing.done():
        raise HTTPException(status_code=409, detail="Standby worker already running")

    async def _worker():
        from app.core.config import get_settings
        from app.core.logging import get_logger
        from app.infrastructure.database import AsyncSessionFactory

        settings = get_settings()
        logger = get_logger(__name__)

        logger.info("standby_worker_start_via_http", poll_seconds=settings.standby_worker_poll_seconds)

        try:
            while getattr(app.state, "standby_worker_running", True):
                async with AsyncSessionFactory() as session:
                    svc = StandbyAgentService(session)
                    await svc.process_due_agents(limit=settings.standby_worker_batch_size)
                    await svc.process_due_digests(limit=settings.standby_worker_batch_size)

                await asyncio.sleep(settings.standby_worker_poll_seconds)
        except asyncio.CancelledError:
            logger.info("standby_worker_cancelled")
        except Exception as exc:
            logger.exception("standby_worker_error", error=str(exc))
        finally:
            app.state.standby_worker_task = None
            app.state.standby_worker_running = False

    app.state.standby_worker_running = True
    app.state.standby_worker_task = asyncio.create_task(_worker())
    return {"status": "started"}


@router.post("/standby-worker/stop")
async def stop_standby_worker(request: Request):
    app = request.app
    task = getattr(app.state, "standby_worker_task", None)
    if not task:
        return {"status": "not_running"}
    app.state.standby_worker_running = False
    try:
        task.cancel()
    except Exception:
        pass
    return {"status": "stopping"}


@router.get("/standby-worker/status")
async def standby_worker_status(request: Request):
    task = getattr(request.app.state, "standby_worker_task", None)
    running = bool(task and not task.done())
    return {"running": running}


@router.get("/standby-agents", response_model=list[StandbyAgentSchema])
async def list_standby_agents(
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    return await svc.list_agents(user_id=user.user_id)


@router.post("/standby-agents", response_model=StandbyAgentSchema, status_code=201)
async def create_standby_agent(
    payload: StandbyAgentCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    logger.info(
        "standby_agent_create_request",
        user_id=user.user_id,
        user_email=user.user_email,
        shipment_id=payload.shipment_id,
        action=payload.action,
        interval_seconds=payload.interval_seconds,
        condition_text=payload.condition_text,
    )
    svc = StandbyAgentService(db)
    agent = await svc.create_agent(user_id=user.user_id, user_email=user.user_email, payload=payload)
    logger.info(
        "standby_agent_create_response",
        agent_id=agent.id,
        user_id=agent.user_id,
        user_email=agent.user_email,
        shipment_id=agent.shipment_id,
        action=agent.action,
        status=agent.status,
        next_run_at=agent.next_run_at,
        trigger_type=agent.trigger_type,
    )
    return agent


@router.patch("/standby-agents/{agent_id}", response_model=StandbyAgentSchema)
async def update_standby_agent(
    agent_id: str,
    payload: StandbyAgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    result = await svc.update_agent(user_id=user.user_id, agent_id=agent_id, payload=payload)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Standby agent '{agent_id}' not found")
    return result


@router.post("/standby-agents/{agent_id}/run", response_model=StandbyAgentSchema)
async def run_standby_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    result = await svc.run_agent_now(user_id=user.user_id, agent_id=agent_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Standby agent '{agent_id}' not found")
    return result


@router.delete("/standby-agents/{agent_id}", status_code=204)
async def delete_standby_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    deleted = await svc.delete_agent(user_id=user.user_id, agent_id=agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Standby agent '{agent_id}' not found")
    return Response(status_code=204)


@router.get("/notifications", response_model=list[UserNotificationSchema])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    return await svc.list_notifications(user_id=user.user_id)


@router.post("/notifications/read", response_model=list[UserNotificationSchema])
async def mark_notifications_read(
    payload: NotificationReadRequest,
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    return await svc.mark_notifications_read(user_id=user.user_id, payload=payload)


@router.get("/agent-outputs", response_model=list[AgentOutputSchema])
async def list_agent_outputs(
    output_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    return await svc.list_outputs(user_id=user.user_id, output_type=output_type)


@router.get("/agent-outputs/{output_id}", response_model=AgentOutputSchema)
async def get_agent_output(
    output_id: str,
    db: AsyncSession = Depends(get_db),
    user: RequestUserContext = Depends(get_request_user_context),
):
    svc = StandbyAgentService(db)
    result = await svc.get_output(user_id=user.user_id, output_id=output_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Agent output '{output_id}' not found")
    return result

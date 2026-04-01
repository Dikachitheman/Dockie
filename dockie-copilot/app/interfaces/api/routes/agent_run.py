"""
AG-UI / Google ADK runtime endpoint.

This exposes the shipment copilot as an AG-UI-compatible streaming endpoint so
the frontend can drive a conversational session over the real ADK runtime.
"""

from __future__ import annotations

import json
import uuid

from ag_ui.core import EventType, RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from ag_ui_adk import ADKAgent
from ag_ui_adk.endpoint import AgentStateRequest
from ag_ui_adk.event_translator import adk_events_to_messages
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.interfaces.api.user_context import RequestUserContext, get_request_user_context
from app.application.adk_agent import (
    CACHED_TOOL_ARGS_STATE_KEY,
    CACHED_TOOL_HIT_STATE_KEY,
    CACHED_TOOL_NAME_STATE_KEY,
    REQUEST_INTENT_KIND_STATE_KEY,
    REQUEST_PROMPT_STATE_KEY,
    REQUEST_RUN_ID_STATE_KEY,
    REQUEST_THREAD_ID_STATE_KEY,
    REQUEST_USER_ID_STATE_KEY,
    SELECTED_SHIPMENT_STATE_KEY,
)
from app.application.agent_plan_cache import (
    build_cached_tool_args,
    get_cached_tool_plan,
    set_cached_tool_plan,
)
from app.infrastructure.agent_audit import append_audit_event, infer_intent_kind, truncate_text

router = APIRouter(prefix="/agent", tags=["agent-run"])


def _classify_run_error(exc: Exception) -> tuple[str, str]:
    text = str(exc)
    lower = text.lower()
    if "503" in lower or "unavailable" in lower or "high demand" in lower:
        return (
            "MODEL_UNAVAILABLE",
            "The model is temporarily overloaded right now. Please try again in a moment.",
        )
    return ("AGENT_ERROR", f"Agent execution failed: {exc}")


def get_adk_agent_dep(request: Request) -> ADKAgent:
    return request.app.state.adk_agent


@router.post("/run")
async def run_agent(
    input_data: RunAgentInput,
    request: Request,
    agent: ADKAgent = Depends(get_adk_agent_dep),
    user: RequestUserContext = Depends(get_request_user_context),
):
    user_id = user.user_id
    state = input_data.state if isinstance(input_data.state, dict) else {}
    shipment_id = state.get(SELECTED_SHIPMENT_STATE_KEY)
    prompt = ""
    if getattr(input_data, "messages", None):
        last_message = input_data.messages[-1]
        prompt = getattr(last_message, "content", "") or ""
    intent_kind = infer_intent_kind(prompt)
    cached_plan = await get_cached_tool_plan(
        user_id=user_id,
        shipment_id=str(shipment_id) if shipment_id else None,
        intent_kind=intent_kind,
    )
    input_data = input_data.model_copy(
        update={
            "state": {
                **state,
                REQUEST_USER_ID_STATE_KEY: user_id,
                REQUEST_PROMPT_STATE_KEY: prompt,
                REQUEST_RUN_ID_STATE_KEY: input_data.run_id,
                REQUEST_THREAD_ID_STATE_KEY: input_data.thread_id,
                REQUEST_INTENT_KIND_STATE_KEY: intent_kind,
                CACHED_TOOL_HIT_STATE_KEY: bool(cached_plan),
                CACHED_TOOL_NAME_STATE_KEY: cached_plan.get("tool_name") if cached_plan else None,
                CACHED_TOOL_ARGS_STATE_KEY: cached_plan.get("tool_args") if cached_plan else None,
            },
            "userId": user_id,
        }
    )

    encoder = EventEncoder(accept=request.headers.get("accept"))

    async def event_generator():
        assistant_chunks: list[str] = []
        used_tool_name: str | None = None
        await append_audit_event(
            {
                "event_type": "run_started",
                "run_id": input_data.run_id,
                "thread_id": input_data.thread_id,
                "user_id": user_id,
                "intent_kind": intent_kind,
                "prompt": truncate_text(prompt, limit=1200),
                "state": {
                    "selected_shipment_id": state.get("selected_shipment_id"),
                    "recent_intent_kind": state.get("recent_intent_kind"),
                    "recent_intent_repeated": state.get("recent_intent_repeated"),
                    "recent_intent_age_seconds": state.get("recent_intent_age_seconds"),
                    "cached_tool_hit": bool(cached_plan),
                    "cached_tool_name": cached_plan.get("tool_name") if cached_plan else None,
                },
            }
        )
        try:
            async for event in agent.run(input_data):
                event_type = getattr(event, "type", None)
                if event_type == EventType.TEXT_MESSAGE_CONTENT:
                    delta = getattr(event, "delta", None)
                    if delta:
                        assistant_chunks.append(str(delta))
                elif event_type == EventType.TOOL_CALL_START:
                    used_tool_name = getattr(event, "tool_call_name", None) or used_tool_name
                    await append_audit_event(
                        {
                            "event_type": "run_tool_progress",
                            "stage": "started",
                            "run_id": input_data.run_id,
                            "thread_id": input_data.thread_id,
                            "user_id": user_id,
                            "intent_kind": intent_kind,
                            "tool_call_id": getattr(event, "tool_call_id", None),
                            "tool_name": getattr(event, "tool_call_name", None),
                        }
                    )
                elif event_type == EventType.TOOL_CALL_END:
                    await append_audit_event(
                        {
                            "event_type": "run_tool_progress",
                            "stage": "completed",
                            "run_id": input_data.run_id,
                            "thread_id": input_data.thread_id,
                            "user_id": user_id,
                            "intent_kind": intent_kind,
                            "tool_call_id": getattr(event, "tool_call_id", None),
                            "tool_name": getattr(event, "tool_call_name", None),
                        }
                    )
                yield encoder.encode(event)
            tool_args = build_cached_tool_args(
                shipment_id=str(shipment_id) if shipment_id else "",
                intent_kind=intent_kind,
                prompt=prompt,
            )
            if used_tool_name and tool_args:
                await set_cached_tool_plan(
                    user_id=user_id,
                    shipment_id=str(shipment_id) if shipment_id else None,
                    intent_kind=intent_kind,
                    tool_name=used_tool_name,
                    tool_args=tool_args,
                )
            await append_audit_event(
                {
                    "event_type": "run_completed",
                    "run_id": input_data.run_id,
                    "thread_id": input_data.thread_id,
                    "user_id": user_id,
                    "intent_kind": intent_kind,
                    "assistant_output": truncate_text("".join(assistant_chunks), limit=4000),
                }
            )
        except Exception as exc:
            code, message = _classify_run_error(exc)
            await append_audit_event(
                {
                    "event_type": "run_failed",
                    "run_id": input_data.run_id,
                    "thread_id": input_data.thread_id,
                    "user_id": user_id,
                    "intent_kind": intent_kind,
                    "error_code": code,
                    "error": str(exc),
                    "assistant_output": truncate_text("".join(assistant_chunks), limit=4000),
                }
            )
            error_event = RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=message,
                code=code,
            )
            yield encoder.encode(error_event)

    return StreamingResponse(
        event_generator(),
        media_type=encoder.get_content_type(),
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agents/state")
async def get_agent_state(
    request_data: AgentStateRequest,
    request: Request,
    agent: ADKAgent = Depends(get_adk_agent_dep),
):
    thread_id = request_data.threadId

    try:
        app_name = request_data.appName or getattr(agent, "_static_app_name", None)
        user_id = (
            request_data.userId
            or request.headers.get("X-Session-ID")
            or getattr(agent, "_static_user_id", None)
        )

        if not app_name or not user_id:
            return JSONResponse(
                content={
                    "threadId": thread_id,
                    "threadExists": False,
                    "state": "{}",
                    "messages": "[]",
                    "error": "appName and userId are required to load agent state",
                }
            )

        session = None
        session_id = None

        metadata = agent._get_session_metadata(thread_id)
        if metadata:
            session_id, cached_app_name, cached_user_id = metadata
            session = await agent._session_manager._session_service.get_session(
                session_id=session_id,
                app_name=cached_app_name,
                user_id=cached_user_id,
            )
            app_name = cached_app_name
            user_id = cached_user_id

        if not session:
            session = await agent._session_manager._find_session_by_thread_id(
                app_name=app_name,
                user_id=user_id,
                thread_id=thread_id,
            )
            if session:
                session_id = session.id
                agent._session_lookup_cache[thread_id] = (session_id, app_name, user_id)
                session = await agent._session_manager._session_service.get_session(
                    session_id=session_id,
                    app_name=app_name,
                    user_id=user_id,
                )

        thread_exists = session is not None
        state = {}
        if thread_exists:
            state = await agent._session_manager.get_session_state(
                session_id=session_id,
                app_name=app_name,
                user_id=user_id,
            ) or {}

        messages = []
        if thread_exists and hasattr(session, "events") and session.events:
            messages = adk_events_to_messages(session.events)

        return JSONResponse(
            content={
                "threadId": thread_id,
                "threadExists": thread_exists,
                "state": json.dumps(state),
                "messages": json.dumps([msg.model_dump(by_alias=True) for msg in messages]),
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "threadId": thread_id,
                "threadExists": False,
                "state": "{}",
                "messages": "[]",
                "error": str(exc),
            },
        )

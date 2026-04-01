"""
Redis-backed Google ADK session service.

Stores ADK sessions, app state, and user state in Redis so agent sessions
survive process restarts and work across multiple workers.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from typing import Any

from redis.asyncio import Redis
from typing_extensions import override

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.events.event import Event
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.sessions import _session_util
from google.adk.sessions.base_session_service import GetSessionConfig, ListSessionsResponse
from google.adk.sessions.session import Session
from google.adk.sessions.state import State

from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisSessionService(BaseSessionService):
    """A Redis implementation of the Google ADK session service."""

    def __init__(self, redis_url: str, prefix: str = "dockie:adk") -> None:
        self._prefix = prefix.rstrip(":")
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def _session_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"{self._prefix}:session:{app_name}:{user_id}:{session_id}"

    def _app_sessions_key(self, app_name: str) -> str:
        return f"{self._prefix}:index:app:{app_name}"

    def _user_sessions_key(self, app_name: str, user_id: str) -> str:
        return f"{self._prefix}:index:user:{app_name}:{user_id}"

    def _app_state_key(self, app_name: str) -> str:
        return f"{self._prefix}:state:app:{app_name}"

    def _user_state_key(self, app_name: str, user_id: str) -> str:
        return f"{self._prefix}:state:user:{app_name}:{user_id}"

    def _decode_scalar(self, raw_value: str) -> Any:
        try:
            return json.loads(raw_value)
        except Exception:
            return raw_value

    def _encode_scalar(self, value: Any) -> str:
        return json.dumps(value)

    async def _get_storage_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Session | None:
        payload = await self._redis.get(self._session_key(app_name, user_id, session_id))
        if payload is None:
            return None
        return Session.model_validate_json(payload)

    async def _save_storage_session(self, session: Session) -> None:
        await self._redis.set(
            self._session_key(session.app_name, session.user_id, session.id),
            session.model_dump_json(by_alias=False),
        )
        await self._redis.sadd(self._app_sessions_key(session.app_name), f"{session.user_id}:{session.id}")
        await self._redis.sadd(self._user_sessions_key(session.app_name, session.user_id), session.id)

    async def _merge_state(self, session: Session) -> Session:
        copied_session = copy.deepcopy(session)

        app_state = await self._redis.hgetall(self._app_state_key(session.app_name))
        if app_state:
            for key, raw_value in app_state.items():
                copied_session.state[State.APP_PREFIX + key] = self._decode_scalar(raw_value)

        user_state = await self._redis.hgetall(self._user_state_key(session.app_name, session.user_id))
        if user_state:
            for key, raw_value in user_state.items():
                copied_session.state[State.USER_PREFIX + key] = self._decode_scalar(raw_value)

        return copied_session

    async def _write_state_deltas(self, app_name: str, user_id: str, state: dict[str, Any] | None) -> dict[str, Any]:
        state_deltas = _session_util.extract_state_delta(state or {})
        if state_deltas["app"]:
            await self._redis.hset(
                self._app_state_key(app_name),
                mapping={key: self._encode_scalar(value) for key, value in state_deltas["app"].items()},
            )
        if state_deltas["user"]:
            await self._redis.hset(
                self._user_state_key(app_name, user_id),
                mapping={key: self._encode_scalar(value) for key, value in state_deltas["user"].items()},
            )
        return state_deltas["session"]

    @override
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        resolved_session_id = session_id.strip() if session_id and session_id.strip() else str(uuid.uuid4())
        existing = await self._get_storage_session(app_name=app_name, user_id=user_id, session_id=resolved_session_id)
        if existing is not None:
            raise AlreadyExistsError(f"Session with id {resolved_session_id} already exists.")

        session_state = await self._write_state_deltas(app_name, user_id, state)
        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=resolved_session_id,
            state=session_state or {},
            last_update_time=time.time(),
        )
        await self._save_storage_session(session)
        return await self._merge_state(session)

    @override
    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        session = await self._get_storage_session(app_name=app_name, user_id=user_id, session_id=session_id)
        if session is None:
            return None

        copied_session = await self._merge_state(session)
        if config:
            if config.num_recent_events:
                copied_session.events = copied_session.events[-config.num_recent_events:]
            if config.after_timestamp:
                copied_session.events = [
                    event for event in copied_session.events if event.timestamp >= config.after_timestamp
                ]
        return copied_session

    @override
    async def list_sessions(self, *, app_name: str, user_id: str | None = None) -> ListSessionsResponse:
        session_refs: list[tuple[str, str]] = []

        if user_id is None:
            members = await self._redis.smembers(self._app_sessions_key(app_name))
            session_refs = [tuple(member.split(":", 1)) for member in members if ":" in member]
        else:
            members = await self._redis.smembers(self._user_sessions_key(app_name, user_id))
            session_refs = [(user_id, session_id) for session_id in members]

        sessions: list[Session] = []
        for session_user_id, session_id in session_refs:
            session = await self._get_storage_session(app_name=app_name, user_id=session_user_id, session_id=session_id)
            if session is None:
                continue
            session.events = []
            sessions.append(await self._merge_state(session))

        sessions.sort(key=lambda item: item.last_update_time, reverse=True)
        return ListSessionsResponse(sessions=sessions)

    @override
    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        await self._redis.delete(self._session_key(app_name, user_id, session_id))
        await self._redis.srem(self._app_sessions_key(app_name), f"{user_id}:{session_id}")
        await self._redis.srem(self._user_sessions_key(app_name, user_id), session_id)

    @override
    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event

        storage_session = await self._get_storage_session(
            app_name=session.app_name,
            user_id=session.user_id,
            session_id=session.id,
        )
        if storage_session is None:
            return event

        await super().append_event(session=session, event=event)
        session.last_update_time = event.timestamp
        storage_session.events.append(event)
        storage_session.last_update_time = event.timestamp

        if event.actions and event.actions.state_delta:
            state_deltas = _session_util.extract_state_delta(event.actions.state_delta)
            if state_deltas["app"]:
                await self._redis.hset(
                    self._app_state_key(session.app_name),
                    mapping={key: self._encode_scalar(value) for key, value in state_deltas["app"].items()},
                )
            if state_deltas["user"]:
                await self._redis.hset(
                    self._user_state_key(session.app_name, session.user_id),
                    mapping={key: self._encode_scalar(value) for key, value in state_deltas["user"].items()},
                )
            if state_deltas["session"]:
                storage_session.state.update(state_deltas["session"])

        await self._save_storage_session(storage_session)
        return event


class ResilientSessionService(BaseSessionService):
    """Prefer Redis-backed sessions, but degrade to memory if Redis fails."""

    def __init__(
        self,
        primary: BaseSessionService,
        fallback: BaseSessionService | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or InMemorySessionService()
        self._degraded = False

    async def _run(self, operation: str, callback):
        service = self._fallback if self._degraded else self._primary
        try:
            return await callback(service)
        except Exception as exc:
            if self._degraded:
                raise
            self._degraded = True
            logger.warning(
                "adk_session_backend_degraded",
                operation=operation,
                error=str(exc),
                primary_backend=type(self._primary).__name__,
                fallback_backend=type(self._fallback).__name__,
            )
            return await callback(self._fallback)

    @override
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        return await self._run(
            "create_session",
            lambda service: service.create_session(
                app_name=app_name,
                user_id=user_id,
                state=state,
                session_id=session_id,
            ),
        )

    @override
    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        return await self._run(
            "get_session",
            lambda service: service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                config=config,
            ),
        )

    @override
    async def list_sessions(self, *, app_name: str, user_id: str | None = None) -> ListSessionsResponse:
        return await self._run(
            "list_sessions",
            lambda service: service.list_sessions(app_name=app_name, user_id=user_id),
        )

    @override
    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        await self._run(
            "delete_session",
            lambda service: service.delete_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            ),
        )

    @override
    async def append_event(self, session: Session, event: Event) -> Event:
        return await self._run(
            "append_event",
            lambda service: service.append_event(session=session, event=event),
        )

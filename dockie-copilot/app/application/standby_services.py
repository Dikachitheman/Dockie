from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from collections import defaultdict

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services import ShipmentService
from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.email import SupabaseEmailClient, build_supabase_email_client
from app.models.orm import AgentOutput, StandbyAgent, StandbyAgentRun, StandbyDigestQueue, UserNotification
from app.schemas.requests import NotificationReadRequest, StandbyAgentCreateRequest, StandbyAgentUpdateRequest
from app.schemas.responses import AgentOutputSchema, StandbyAgentSchema, UserNotificationSchema

logger = get_logger(__name__)
settings = get_settings()


@dataclass(slots=True)
class StandbyEvaluationResult:
    matched: bool
    result_text: str
    action_executed: str | None = None


class StandbyAgentService:
    def __init__(self, session: AsyncSession, email_client: SupabaseEmailClient | None = None) -> None:
        self._session = session
        self._shipment_service = ShipmentService(session)
        self._email_client = email_client or build_supabase_email_client()

    async def list_agents(self, *, user_id: str) -> list[StandbyAgentSchema]:
        result = await self._session.execute(
            select(StandbyAgent)
            .where(StandbyAgent.user_id == user_id)
            .order_by(StandbyAgent.created_at.desc())
        )
        return [StandbyAgentSchema.model_validate(row) for row in result.scalars().all()]

    async def create_agent(
        self,
        *,
        user_id: str,
        user_email: str | None,
        payload: StandbyAgentCreateRequest,
    ) -> StandbyAgentSchema:
        now = datetime.now(timezone.utc)
        trigger_type, rule_payload = await self._compile_rule(payload.condition_text)
        agent = StandbyAgent(
            user_id=user_id,
            user_email=user_email,
            shipment_id=payload.shipment_id,
            condition_text=payload.condition_text.strip(),
            trigger_type=trigger_type,
            action=payload.action,
            interval_seconds=payload.interval_seconds,
            cooldown_seconds=settings.standby_default_cooldown_seconds,
            status="active",
            rule_payload=rule_payload,
            next_run_at=now,
        )
        self._session.add(agent)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(agent)
        return StandbyAgentSchema.model_validate(agent)

    async def update_agent(
        self,
        *,
        user_id: str,
        agent_id: str,
        payload: StandbyAgentUpdateRequest,
    ) -> StandbyAgentSchema | None:
        agent = await self._get_agent(user_id=user_id, agent_id=agent_id)
        if agent is None:
            return None

        if payload.condition_text is not None:
            trigger_type, rule_payload = await self._compile_rule(payload.condition_text)
            agent.condition_text = payload.condition_text.strip()
            agent.trigger_type = trigger_type
            agent.rule_payload = rule_payload
        if payload.action is not None:
            agent.action = payload.action
        if payload.interval_seconds is not None:
            agent.interval_seconds = payload.interval_seconds
        if payload.status is not None:
            agent.status = payload.status
        if agent.status == "active" and agent.next_run_at is None:
            agent.next_run_at = datetime.now(timezone.utc)

        await self._session.commit()
        await self._session.refresh(agent)
        return StandbyAgentSchema.model_validate(agent)

    async def delete_agent(self, *, user_id: str, agent_id: str) -> bool:
        agent = await self._get_agent(user_id=user_id, agent_id=agent_id)
        if agent is None:
            return False

        # Remove user-visible artifacts tied to the agent so deletion fully clears it
        # from notifications, output lists, and pending digest processing.
        await self._session.execute(
            delete(UserNotification)
            .where(UserNotification.user_id == user_id)
            .where(UserNotification.agent_id == agent_id)
        )
        await self._session.execute(
            delete(AgentOutput)
            .where(AgentOutput.user_id == user_id)
            .where(AgentOutput.agent_id == agent_id)
        )
        await self._session.execute(
            delete(StandbyDigestQueue)
            .where(StandbyDigestQueue.user_id == user_id)
            .where(StandbyDigestQueue.agent_id == agent_id)
        )
        await self._session.delete(agent)
        await self._session.commit()
        logger.info("standby_agent_deleted", agent_id=agent_id, user_id=user_id)
        return True

    async def run_agent_now(self, *, user_id: str, agent_id: str) -> StandbyAgentSchema | None:
        agent = await self._get_agent(user_id=user_id, agent_id=agent_id)
        if agent is None:
            return None

        await self._evaluate_and_record(agent)
        await self._session.commit()
        await self._session.refresh(agent)
        return StandbyAgentSchema.model_validate(agent)

    async def process_due_agents(self, *, limit: int | None = None) -> int:
        now = datetime.now(timezone.utc)
        batch_size = limit or settings.standby_worker_batch_size
        result = await self._session.execute(
            select(StandbyAgent)
            .where(StandbyAgent.status == "active")
            .where(
                or_(
                    StandbyAgent.next_run_at.is_(None),
                    StandbyAgent.next_run_at <= now,
                )
            )
            .order_by(StandbyAgent.next_run_at.asc().nullsfirst(), StandbyAgent.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        agents = result.scalars().all()
        if not agents:
            return 0

        processed = 0
        for agent in agents:
            await self._evaluate_and_record(agent)
            processed += 1

        await self._session.commit()
        logger.info("standby_agents_processed", count=processed)
        return processed

    async def process_due_digests(self, *, limit: int | None = None) -> int:
        now = datetime.now(timezone.utc)
        batch_size = limit or settings.standby_worker_batch_size
        result = await self._session.execute(
            select(StandbyDigestQueue)
            .where(StandbyDigestQueue.status == "pending")
            .where(StandbyDigestQueue.digest_due_at <= now)
            .order_by(StandbyDigestQueue.digest_due_at.asc(), StandbyDigestQueue.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = result.scalars().all()
        if not rows:
            return 0

        grouped: dict[tuple[str, str], list[StandbyDigestQueue]] = defaultdict(list)
        for row in rows:
            if row.user_email:
                grouped[(row.user_id, row.user_email)].append(row)

        sent_count = 0
        for (_, user_email), items in grouped.items():
            subject = "Dockie standby digest"
            lines = ["Here is your latest standby-agent digest:", ""]
            for item in items:
                lines.append(f"- {item.title}: {item.detail}")
            body_text = "\n".join(lines)

            sent = await self._email_client.send_standby_email(
                to_email=user_email,
                subject=subject,
                body_text=body_text,
                metadata={"digest_item_count": len(items)},
            )
            if not sent:
                continue

            sent_at = datetime.now(timezone.utc)
            for item in items:
                item.status = "sent"
                item.sent_at = sent_at
                sent_count += 1

        if sent_count:
            await self._session.commit()
        logger.info("standby_digests_processed", count=sent_count)
        return sent_count

    async def list_notifications(self, *, user_id: str) -> list[UserNotificationSchema]:
        result = await self._session.execute(
            select(UserNotification)
            .where(UserNotification.user_id == user_id)
            .order_by(UserNotification.created_at.desc())
            .limit(100)
        )
        return [UserNotificationSchema.model_validate(row) for row in result.scalars().all()]

    async def list_outputs(self, *, user_id: str, output_type: str | None = None) -> list[AgentOutputSchema]:
        stmt = (
            select(AgentOutput)
            .where(AgentOutput.user_id == user_id)
            .order_by(AgentOutput.created_at.desc())
            .limit(100)
        )
        if output_type:
            stmt = stmt.where(AgentOutput.output_type == output_type)
        result = await self._session.execute(stmt)
        return [AgentOutputSchema.model_validate(row) for row in result.scalars().all()]

    async def get_output(self, *, user_id: str, output_id: str) -> AgentOutputSchema | None:
        result = await self._session.execute(
            select(AgentOutput)
            .where(AgentOutput.user_id == user_id)
            .where(AgentOutput.id == output_id)
            .limit(1)
        )
        output = result.scalar_one_or_none()
        return AgentOutputSchema.model_validate(output) if output else None

    async def mark_notifications_read(
        self,
        *,
        user_id: str,
        payload: NotificationReadRequest,
    ) -> list[UserNotificationSchema]:
        now = datetime.now(timezone.utc)
        stmt = (
            update(UserNotification)
            .where(UserNotification.user_id == user_id)
            .values(unread=False, read_at=now)
        )
        if payload.notification_ids:
            stmt = stmt.where(UserNotification.id.in_(payload.notification_ids))
        await self._session.execute(stmt)
        await self._session.commit()
        return await self.list_notifications(user_id=user_id)

    async def _get_agent(self, *, user_id: str, agent_id: str) -> StandbyAgent | None:
        result = await self._session.execute(
            select(StandbyAgent)
            .where(StandbyAgent.user_id == user_id)
            .where(StandbyAgent.id == agent_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _compile_rule(self, condition_text: str) -> tuple[str, dict[str, str]]:
        trigger = await self._classify_trigger_semantic(condition_text)
        return trigger, {"trigger": trigger}

    async def _classify_trigger_semantic(self, condition_text: str) -> str:
        """Use Gemini to classify condition_text into a trigger type.
        Falls back to keyword matching if the API key is absent or the call fails."""
        if settings.google_api_key:
            try:
                from google import genai  # bundled with google-adk

                client = genai.Client(api_key=settings.google_api_key)
                prompt = (
                    "Classify the following shipment-monitoring condition into exactly one of these "
                    "trigger types: freshness, eta_shift, anchorage_status, lagos_arrival, "
                    "demurrage_exposure, general_watch.\n\n"
                    "Rules:\n"
                    "- freshness: concerns data staleness, age of updates, or missing recent data\n"
                    "- eta_shift: concerns arrival time changes, delays, or schedule revisions\n"
                    "- anchorage_status: concerns a vessel anchoring, waiting at anchor, or anchorage events\n"
                    "- lagos_arrival: concerns arrival at Lagos or Nigerian ports\n"
                    "- demurrage_exposure: concerns demurrage fees, port detention costs, or storage charges\n"
                    "- general_watch: anything else that doesn't clearly fit the above\n\n"
                    f'Condition: "{condition_text}"\n\n'
                    "Reply with only the trigger type name, nothing else."
                )
                response = client.models.generate_content(
                    model=settings.adk_model,
                    contents=prompt,
                )
                classified = response.text.strip().lower()
                valid = {"freshness", "eta_shift", "anchorage_status", "lagos_arrival", "demurrage_exposure", "general_watch"}
                if classified in valid:
                    logger.info("standby_rule_classified_semantic", trigger=classified, condition=condition_text)
                    return classified
                logger.warning("standby_rule_classify_unexpected_response", response=classified)
            except Exception as exc:
                logger.warning("standby_rule_classify_failed", error=str(exc))

        # Keyword fallback
        lower = condition_text.lower()
        if "fresh" in lower:
            return "freshness"
        if "eta" in lower:
            return "eta_shift"
        if "anchor" in lower:
            return "anchorage_status"
        if "lagos" in lower:
            return "lagos_arrival"
        if "demurrage" in lower:
            return "demurrage_exposure"
        return "general_watch"

    async def _evaluate_and_record(self, agent: StandbyAgent) -> StandbyEvaluationResult:
        now = datetime.now(timezone.utc)
        logger.info(
            "standby_agent_check_started",
            agent_id=agent.id,
            user_id=agent.user_id,
            shipment_id=agent.shipment_id,
            trigger_type=agent.trigger_type,
            action=agent.action,
            status=agent.status,
        )
        run = StandbyAgentRun(agent_id=agent.id, started_at=now)
        self._session.add(run)
        await self._session.flush()

        result = await self._evaluate_agent(agent)
        base_result_text = result.result_text
        run.finished_at = datetime.now(timezone.utc)
        run.matched = result.matched

        agent.last_checked_at = now
        agent.next_run_at = now + timedelta(seconds=agent.interval_seconds)

        cooldown_allows_fire = (
            agent.last_fired_at is None
            or agent.cooldown_seconds <= 0
            or (now - agent.last_fired_at).total_seconds() >= agent.cooldown_seconds
        )
        should_fire = result.matched and not agent.last_match_state and cooldown_allows_fire
        logger.info(
            "standby_agent_fire_decision",
            agent_id=agent.id,
            condition_matched=result.matched,
            will_fire=should_fire,
            last_match_state=agent.last_match_state,
            cooldown_allows_fire=cooldown_allows_fire,
            trigger_type=agent.trigger_type,
            shipment_id=agent.shipment_id,
        )
        output = None
        if should_fire:
            agent.last_fired_at = now
            agent.fire_count += 1
            agent.status = "fired"
            result.action_executed, output = await self._dispatch_agent_action(agent, base_result_text)
            await self._create_notification_for_agent(agent, base_result_text, action_executed=result.action_executed, output=output)
            if output is not None:
                result.result_text = f"{base_result_text} {output.preview_text}"
        elif result.matched and agent.last_match_state:
            agent.status = "fired"
            result.result_text = (
                "Condition still true. No new fire because it already fired before. "
                f"Latest signal: {base_result_text}"
            )
            result.action_executed = "suppressed"
        elif result.matched and not cooldown_allows_fire:
            logger.info("standby_agent_cooldown_suppressed", agent_id=agent.id)
            agent.status = "fired"
            result.result_text = (
                "Condition still true. No new fire because cooldown is still active. "
                f"Latest signal: {base_result_text}"
            )
            result.action_executed = "suppressed"
        elif not result.matched and agent.status != "paused":
            agent.status = "active"

        agent.last_result = result.result_text
        run.result_text = result.result_text
        run.action_executed = result.action_executed
        agent.last_match_state = result.matched
        logger.info(
            "standby_agent_check_finished",
            agent_id=agent.id,
            user_id=agent.user_id,
            shipment_id=agent.shipment_id,
            matched=result.matched,
            action_executed=result.action_executed,
            status=agent.status,
            fire_count=agent.fire_count,
            next_run_at=agent.next_run_at,
            result_text=result.result_text,
        )
        return result

    async def _evaluate_agent(self, agent: StandbyAgent) -> StandbyEvaluationResult:
        shipment_ids: list[str]
        if agent.shipment_id:
            shipment_ids = [agent.shipment_id]
        else:
            shipments = await self._shipment_service.list_shipments()
            shipment_ids = [shipment.id for shipment in shipments if shipment.status != "delivered"]

        if not shipment_ids:
            return StandbyEvaluationResult(matched=False, result_text="No shipments available for this standby agent.")

        shipment_summaries: list[dict] = []
        for shipment_id in shipment_ids:
            status = await self._shipment_service.get_shipment_status(shipment_id)
            if status is None:
                continue

            if agent.trigger_type == "general_watch":
                shipment_summaries.append({
                    "shipment_id": shipment_id,
                    "booking_ref": status.booking_ref,
                    "freshness_warning": status.freshness_warning,
                    "eta_freshness": status.eta_confidence.freshness if status.eta_confidence else None,
                    "eta_estimate": str(status.eta_confidence.declared_eta) if status.eta_confidence and status.eta_confidence.declared_eta else None,
                    "navigation_status": status.latest_position.navigation_status if status.latest_position else None,
                    "destination": status.latest_position.destination_text if status.latest_position else None,
                    "speed_knots": status.latest_position.sog_knots if status.latest_position else None,
                })
                continue

            if agent.trigger_type == "freshness" and status.freshness_warning:
                return StandbyEvaluationResult(
                    matched=True,
                    result_text=f"{status.booking_ref} has a freshness warning: {status.freshness_warning}",
                )

            if agent.trigger_type == "eta_shift" and status.eta_confidence.freshness != "fresh":
                return StandbyEvaluationResult(
                    matched=True,
                    result_text=(
                        f"{status.booking_ref} should be reviewed because ETA freshness is "
                        f"{status.eta_confidence.freshness}."
                    ),
                )

            nav_status = (status.latest_position.navigation_status or "") if status.latest_position else ""
            if agent.trigger_type == "anchorage_status" and "anchor" in nav_status.lower():
                return StandbyEvaluationResult(
                    matched=True,
                    result_text=f"{status.booking_ref} is showing anchorage status in live tracking.",
                )
            if agent.trigger_type == "anchorage_status":
                observations = await self._shipment_service.get_port_observations(shipment_id)
                anchor_observation = self._find_anchor_observation(observations)
                if anchor_observation is not None:
                    return StandbyEvaluationResult(
                        matched=True,
                        result_text=(
                            f"{status.booking_ref} is showing anchorage status from port observation "
                            f"at {anchor_observation.port_locode}."
                        ),
                    )

            if agent.trigger_type == "lagos_arrival":
                destination = (status.latest_position.destination_text or "") if status.latest_position else ""
                if "lag" in (destination.lower() + (status.booking_ref.lower() if status.booking_ref else "")):
                    return StandbyEvaluationResult(
                        matched=True,
                        result_text=f"{status.booking_ref} is showing a Lagos-bound arrival signal.",
                    )
                shipment = await self._shipment_service.get_shipment_detail(shipment_id)
                if shipment and (shipment.discharge_port or "").lower().find("lag") >= 0 and status.latest_position:
                    return StandbyEvaluationResult(
                        matched=True,
                        result_text=f"{status.booking_ref} is moving with live tracking toward Lagos.",
                    )

            if agent.trigger_type == "demurrage_exposure":
                exposure = await self._shipment_service.get_demurrage_exposure(shipment_id)
                if exposure is not None and exposure.risk_level in {"medium", "high"}:
                    return StandbyEvaluationResult(
                        matched=True,
                        result_text=(
                            f"{shipment_id} has {exposure.risk_level} demurrage exposure "
                            f"at projected NGN {exposure.projected_cost_ngn:,.0f}."
                        ),
                    )

        if shipment_summaries:
            return await self._evaluate_general_watch(agent, shipment_summaries)

        return StandbyEvaluationResult(
            matched=False,
            result_text="Condition not met on the latest evaluation round.",
        )

    async def _evaluate_general_watch(self, agent: StandbyAgent, shipment_summaries: list[dict]) -> StandbyEvaluationResult:
        """Use Gemini to evaluate an open-ended condition against live shipment data."""
        if not settings.google_api_key:
            return StandbyEvaluationResult(
                matched=False,
                result_text="general_watch condition requires GOOGLE_API_KEY to evaluate semantically.",
            )
        try:
            from google import genai

            client = genai.Client(api_key=settings.google_api_key)
            context = json.dumps(shipment_summaries, default=str, indent=2)
            prompt = (
                "You are a shipment monitoring assistant. Given the condition and live shipment data below, "
                "decide whether the condition is currently met.\n\n"
                f'Condition: "{agent.condition_text}"\n\n'
                f"Shipment data:\n{context}\n\n"
                "Reply with exactly two lines:\n"
                "Line 1: yes or no\n"
                "Line 2: one sentence explaining why"
            )
            response = client.models.generate_content(
                model=settings.adk_model,
                contents=prompt,
            )
            lines = [l.strip() for l in response.text.strip().splitlines() if l.strip()]
            matched = len(lines) > 0 and lines[0].lower().startswith("yes")
            reason = lines[1] if len(lines) > 1 else lines[0] if lines else "No reason provided."
            logger.info("standby_general_watch_evaluated", agent_id=agent.id, matched=matched, reason=reason)
            return StandbyEvaluationResult(matched=matched, result_text=reason)
        except Exception as exc:
            logger.warning("standby_general_watch_eval_failed", error=str(exc))
            return StandbyEvaluationResult(matched=False, result_text=f"Semantic evaluation failed: {exc}")

    async def _create_notification_for_agent(
        self,
        agent: StandbyAgent,
        detail: str,
        *,
        action_executed: str | None,
        output: AgentOutput | None,
    ) -> None:
        action_detail = action_executed or agent.action
        notification = UserNotification(
            user_id=agent.user_id,
            agent_id=agent.id,
            output_id=output.id if output is not None else None,
            channel="in_app" if agent.action == "notify" else agent.action,
            title="Standby agent fired",
            detail=f"{detail} Action: {action_detail}.",
            unread=True,
        )
        self._session.add(notification)

    async def _dispatch_agent_action(self, agent: StandbyAgent, detail: str) -> tuple[str | None, AgentOutput | None]:
        if agent.action == "notify":
            return "in_app_notified", None

        if agent.action == "log":
            logger.info(
                "standby_log_action_fired",
                agent_id=agent.id,
                user_id=agent.user_id,
                shipment_id=agent.shipment_id,
                trigger_type=agent.trigger_type,
                detail=detail,
            )
            return "log_written", None

        if agent.action == "email":
            if not agent.user_email:
                logger.warning("standby_email_missing_recipient", agent_id=agent.id, user_id=agent.user_id)
                return None, None
            sent = await self._email_client.send_standby_email(
                to_email=agent.user_email,
                subject="Dockie standby agent alert",
                body_text=detail,
                metadata={
                    "agent_id": agent.id,
                    "user_id": agent.user_id,
                    "shipment_id": agent.shipment_id,
                    "trigger_type": agent.trigger_type,
                },
            )
            if not sent:
                return None, None
            output = await self._create_output(
                agent=agent,
                output_type="email",
                title="Standby email alert",
                content=detail,
                preview_text=f"Sent email to {agent.user_email}.",
                metadata={"recipient": agent.user_email},
            )
            return "email_sent", output

        if agent.action == "digest":
            self._session.add(
                StandbyDigestQueue(
                    user_id=agent.user_id,
                    user_email=agent.user_email,
                    agent_id=agent.id,
                    shipment_id=agent.shipment_id,
                    title="Dockie standby digest item",
                    detail=detail,
                    digest_due_at=self._next_digest_due_at(),
                    status="pending",
                )
            )
            return "digest_queued", None

        if agent.action in {"report", "spreadsheet", "document"}:
            output = await self._create_generated_output(agent=agent, detail=detail, output_type=agent.action)
            if output is None:
                return None, None
            return f"{agent.action}_generated", output

        return None, None

    async def _create_generated_output(self, *, agent: StandbyAgent, detail: str, output_type: str) -> AgentOutput | None:
        shipment_ref = agent.shipment_id or "all-active-shipments"
        if output_type == "spreadsheet":
            escaped_detail = detail.replace('"', "'")
            content = "\n".join(
                [
                    "booking_ref,status,trigger,detail",
                    f'{shipment_ref},fired,{agent.trigger_type},"{escaped_detail}"',
                ]
            )
            preview = "Generated spreadsheet with the latest triggered shipment state."
            title = "Standby spreadsheet export"
        elif output_type == "report":
            content = "\n".join(
                [
                    "# Dockie Standby Report",
                    "",
                    f"- Shipment scope: {shipment_ref}",
                    f"- Trigger: {agent.trigger_type}",
                    f"- Condition: {agent.condition_text}",
                    f"- Result: {detail}",
                ]
            )
            preview = "Generated report summarizing the fired standby condition."
            title = "Standby report"
        else:
            content = "\n".join(
                [
                    "Dockie standby draft document",
                    "",
                    f"Shipment scope: {shipment_ref}",
                    f"Condition: {agent.condition_text}",
                    f"Result: {detail}",
                ]
            )
            preview = "Generated draft document from the fired standby condition."
            title = "Standby draft document"
        return await self._create_output(
            agent=agent,
            output_type=output_type,
            title=title,
            content=content,
            preview_text=preview,
            metadata={"trigger_type": agent.trigger_type},
        )

    async def _create_output(
        self,
        *,
        agent: StandbyAgent,
        output_type: str,
        title: str,
        content: str,
        preview_text: str,
        metadata: dict | None = None,
    ) -> AgentOutput:
        output = AgentOutput(
            user_id=agent.user_id,
            agent_id=agent.id,
            shipment_id=agent.shipment_id,
            output_type=output_type,
            title=title,
            preview_text=preview_text,
            content=content,
            metadata_=metadata,
        )
        self._session.add(output)
        await self._session.flush()
        return output

    def _next_digest_due_at(self) -> datetime:
        now = datetime.now(timezone.utc)
        due_at = now.replace(
            hour=settings.standby_digest_send_hour_local,
            minute=0,
            second=0,
            microsecond=0,
        )
        if due_at <= now:
            due_at += timedelta(days=1)
        return due_at

    def _find_anchor_observation(self, observations) -> object | None:
        if not observations:
            return None

        latest = max(observations, key=lambda observation: observation.observed_at)
        # Only check structured fields (status, event_type) — not free-text detail,
        # which may mention "anchorage" in a negative context (e.g. "not yet reached anchorage").
        haystack = " ".join([latest.status or "", latest.event_type or ""]).lower()
        if "anchor" in haystack:
            return latest
        return None

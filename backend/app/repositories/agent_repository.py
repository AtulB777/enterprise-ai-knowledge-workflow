import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.metrics import AGENT_STEPS
from app.models.agent_enums import (
    AgentRunStatus,
    AgentStepState,
    ApprovalDecision,
    ToolCallStatus,
    ToolRiskLevel,
)
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.approval import Approval
from app.models.tool_call import ToolCall

logger = logging.getLogger("app.agents")


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        goal: str,
        max_steps: int,
        max_runtime_seconds: int,
        max_tool_calls: int,
    ) -> AgentRun:
        run = AgentRun(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            goal=goal,
            status=AgentRunStatus.RUNNING,
            max_steps=max_steps,
            max_runtime_seconds=max_runtime_seconds,
            max_tool_calls=max_tool_calls,
            started_at=datetime.now(UTC),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_run_by_id_for_org(
        self, *, run_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AgentRun | None:
        result = await self._session.execute(
            select(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.organization_id == organization_id)
            .options(
                selectinload(AgentRun.steps),
                selectinload(AgentRun.tool_calls).selectinload(ToolCall.approval),
            )
        )
        return result.scalar_one_or_none()

    async def list_runs_for_org(
        self, *, organization_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[AgentRun], int]:
        count_result = await self._session.execute(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.organization_id == organization_id)
        )
        total = count_result.scalar_one()

        result = await self._session.execute(
            select(AgentRun)
            .where(AgentRun.organization_id == organization_id)
            .order_by(AgentRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def add_step(
        self,
        run: AgentRun,
        *,
        step_index: int,
        state: AgentStepState,
        reasoning: str,
        raw_action_json: dict[str, Any] | None = None,
        tool_call_id: uuid.UUID | None = None,
    ) -> AgentStep:
        step = AgentStep(
            agent_run_id=run.id,
            step_index=step_index,
            state=state,
            reasoning=reasoning,
            raw_action_json=raw_action_json,
            tool_call_id=tool_call_id,
        )
        self._session.add(step)
        await self._session.flush()
        # Setting agent_run_id directly (rather than the `run` relationship
        # attribute) does not trigger SQLAlchemy's bidirectional sync, so
        # run.steps would otherwise stay stale for the rest of this run's
        # execution — not just in the final API response, but for every
        # subsequent _build_transcript() call within the same loop.
        run.steps.append(step)
        AGENT_STEPS.labels(state=state.value).inc()
        logger.info(
            "agent_step",
            extra={
                "agent_run_id": str(run.id),
                "step_index": step_index,
                "state": state.value,
                "tool_call_id": str(tool_call_id) if tool_call_id is not None else None,
            },
        )
        return step

    async def add_tool_call(
        self,
        run: AgentRun,
        *,
        tool_name: str,
        risk_level: ToolRiskLevel,
        input_data: dict[str, Any],
    ) -> ToolCall:
        tool_call = ToolCall(
            agent_run_id=run.id,
            tool_name=tool_name,
            risk_level=risk_level,
            input_data=input_data,
            status=ToolCallStatus.PENDING,
        )
        self._session.add(tool_call)
        await self._session.flush()
        # Same rationale as add_step above.
        run.tool_calls.append(tool_call)
        logger.info(
            "tool_call_selected",
            extra={
                "agent_run_id": str(run.id),
                "tool_call_id": str(tool_call.id),
                "tool_name": tool_name,
                "risk_level": risk_level.value,
            },
        )
        return tool_call

    async def mark_tool_call_awaiting_approval(self, tool_call: ToolCall) -> Approval:
        tool_call.status = ToolCallStatus.AWAITING_APPROVAL
        # Constructing with tool_call=tool_call (the relationship attribute)
        # rather than tool_call_id=tool_call.id (the raw FK) triggers
        # back_populates, so tool_call.approval is set in-memory immediately
        # — using the raw FK bypasses the ORM relationship sync entirely,
        # leaving tool_call.approval unset and requiring an async lazy load
        # (which fails) on next access. Same root cause as the add_step/
        # add_tool_call fix above, via a different mechanism since this is a
        # scalar relationship rather than a collection.
        approval = Approval(tool_call=tool_call, requested_at=datetime.now(UTC))
        self._session.add(approval)
        await self._session.flush()
        logger.info(
            "tool_call_awaiting_approval",
            extra={"tool_call_id": str(tool_call.id), "tool_name": tool_call.tool_name},
        )
        return approval

    async def mark_tool_call_executed(
        self, tool_call: ToolCall, *, output_data: dict[str, Any]
    ) -> None:
        tool_call.status = ToolCallStatus.EXECUTED
        tool_call.output_data = output_data
        tool_call.executed_at = datetime.now(UTC)
        await self._session.flush()
        logger.info(
            "tool_call_executed",
            extra={"tool_call_id": str(tool_call.id), "tool_name": tool_call.tool_name},
        )

    async def mark_tool_call_failed(self, tool_call: ToolCall, *, error_message: str) -> None:
        tool_call.status = ToolCallStatus.FAILED
        tool_call.error_message = error_message
        tool_call.executed_at = datetime.now(UTC)
        await self._session.flush()
        logger.warning(
            "tool_call_failed",
            extra={
                "tool_call_id": str(tool_call.id),
                "tool_name": tool_call.tool_name,
                "reason": error_message,
            },
        )

    async def mark_tool_call_rejected(self, tool_call: ToolCall) -> None:
        tool_call.status = ToolCallStatus.REJECTED
        await self._session.flush()
        logger.info(
            "tool_call_rejected",
            extra={"tool_call_id": str(tool_call.id), "tool_name": tool_call.tool_name},
        )

    async def get_approval_by_id_for_org(
        self, *, approval_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Approval | None:
        result = await self._session.execute(
            select(Approval)
            .join(ToolCall, ToolCall.id == Approval.tool_call_id)
            .join(AgentRun, AgentRun.id == ToolCall.agent_run_id)
            .where(Approval.id == approval_id, AgentRun.organization_id == organization_id)
            .options(selectinload(Approval.tool_call).selectinload(ToolCall.run))
        )
        return result.scalar_one_or_none()

    async def decide_approval(
        self,
        approval: Approval,
        *,
        decision: ApprovalDecision,
        decided_by_user_id: uuid.UUID,
        notes: str | None,
    ) -> None:
        approval.status = decision
        approval.decided_at = datetime.now(UTC)
        approval.decided_by_user_id = decided_by_user_id
        approval.notes = notes
        await self._session.flush()
        logger.info(
            "approval_decided",
            extra={
                "approval_id": str(approval.id),
                "decision": decision.value,
                "decided_by_user_id": str(decided_by_user_id),
            },
        )

    async def update_run_status(
        self,
        run: AgentRun,
        *,
        status: AgentRunStatus,
        final_answer: str | None = None,
        error_message: str | None = None,
        completed: bool = False,
    ) -> None:
        run.status = status
        if final_answer is not None:
            run.final_answer = final_answer
        if error_message is not None:
            run.error_message = error_message
        if completed:
            run.completed_at = datetime.now(UTC)
        await self._session.commit()

    async def increment_step_count(self, run: AgentRun) -> None:
        run.step_count += 1
        await self._session.flush()

"""The agent state machine (spec §21/§26, ADR-005, ADR-012). Orchestrates
the planner, tool execution, and human-approval gating around the
AgentRepository as the single source of truth for a run's state.

Execution is synchronous within one call to start_run()/resume_after_approval()
up to MAX_STEPS/MAX_RUNTIME_SECONDS — see ADR-012 decision 2 for why, and
for the known trade-off (no cross-process resumability) this implies.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.agent_enums import (
    AgentRunStatus,
    AgentStepState,
    ApprovalDecision,
    ToolCallStatus,
    ToolRiskLevel,
)
from app.models.agent_run import AgentRun
from app.models.membership import MembershipRole
from app.models.tool_call import ToolCall
from app.repositories.agent_repository import AgentRepository
from app.services.agents.planner import (
    FinalAnswerAction,
    PlannerParseError,
    ToolCallAction,
    plan_next_action,
)
from app.services.agents.tools.base import Tool, ToolExecutionContext
from app.services.agents.tools.registry import get_tool, list_tools
from app.services.document_service import DocumentService
from app.services.exceptions import ServiceError
from app.services.llm.provider import LLMMessage, LLMProvider
from app.services.search_service import SearchService


class AgentRunNotFoundError(ServiceError):
    pass


class ApprovalNotFoundError(ServiceError):
    pass


class ApprovalAlreadyDecidedError(ServiceError):
    pass


class ApprovalPermissionDeniedError(ServiceError):
    pass


def _available_tools(user_role: MembershipRole) -> list[Tool[Any]]:
    """ADR-012 decision 4: the agent may only select tools the initiating
    user's own role would already be permitted to use directly.
    """
    return [tool for tool in list_tools() if user_role in tool.allowed_roles]


class AgentService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        llm_provider: LLMProvider,
        search_service: SearchService,
        document_service: DocumentService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._llm_provider = llm_provider
        self._search_service = search_service
        self._document_service = document_service
        self._agents = AgentRepository(session)

    async def start_run(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: MembershipRole,
        goal: str,
    ) -> AgentRun:
        created = await self._agents.create_run(
            organization_id=organization_id,
            created_by_user_id=user_id,
            goal=goal,
            max_steps=self._settings.agent_max_steps,
            max_runtime_seconds=self._settings.agent_max_runtime_seconds,
            max_tool_calls=self._settings.agent_max_tool_calls,
        )
        await self._session.commit()
        # A freshly created object's `.steps`/`.tool_calls` collections are
        # not eager-loaded (only get_run_by_id_for_org's query loads them),
        # so accessing them in _run_loop would otherwise attempt an async
        # lazy load and fail with MissingGreenlet — re-fetch through the
        # eager-loaded path before the loop touches either collection.
        run = await self._agents.get_run_by_id_for_org(
            run_id=created.id, organization_id=organization_id
        )
        assert run is not None  # just created in the same transaction
        await self._run_loop(run, user_role=user_role)
        return run

    async def get_run(self, *, organization_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
        run = await self._agents.get_run_by_id_for_org(
            run_id=run_id, organization_id=organization_id
        )
        if run is None:
            raise AgentRunNotFoundError(str(run_id))
        return run

    async def list_runs(
        self, *, organization_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[AgentRun], int]:
        return await self._agents.list_runs_for_org(
            organization_id=organization_id, limit=limit, offset=offset
        )

    async def decide_approval(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
        approved: bool,
        decided_by_user_id: uuid.UUID,
        user_role: MembershipRole,
        notes: str | None,
    ) -> AgentRun:
        approval = await self._agents.get_approval_by_id_for_org(
            approval_id=approval_id, organization_id=organization_id
        )
        if approval is None:
            raise ApprovalNotFoundError(str(approval_id))
        if approval.status != ApprovalDecision.PENDING:
            raise ApprovalAlreadyDecidedError(str(approval_id))

        tool_call = approval.tool_call
        # Same rationale as start_run: tool_call.run is loaded via a
        # selectinload chain that only reaches the AgentRun row itself, not
        # its own .steps/.tool_calls collections — re-fetch through the
        # fully eager-loaded path before _run_loop touches either.
        run = await self._agents.get_run_by_id_for_org(
            run_id=tool_call.run.id, organization_id=organization_id
        )
        assert run is not None  # resolved via this same organization_id above

        tool = get_tool(tool_call.tool_name)
        assert tool is not None  # guaranteed by the run loop that created this ToolCall
        if user_role not in tool.allowed_roles:
            raise ApprovalPermissionDeniedError(
                f"Role '{user_role.value}' cannot approve actions requiring the "
                f"'{tool_call.tool_name}' tool."
            )

        if approved:
            await self._agents.decide_approval(
                approval,
                decision=ApprovalDecision.APPROVED,
                decided_by_user_id=decided_by_user_id,
                notes=notes,
            )
            await self._execute_tool_call(run, tool, tool_call, user_role)
            await self._agents.update_run_status(run, status=AgentRunStatus.RUNNING)
            await self._run_loop(run, user_role=user_role)
        else:
            await self._agents.decide_approval(
                approval,
                decision=ApprovalDecision.REJECTED,
                decided_by_user_id=decided_by_user_id,
                notes=notes,
            )
            await self._agents.mark_tool_call_rejected(tool_call)
            await self._agents.add_step(
                run,
                step_index=run.step_count,
                state=AgentStepState.OBSERVATION,
                reasoning="A human reviewer rejected this proposed action. Stopping the run.",
                tool_call_id=tool_call.id,
            )
            await self._agents.increment_step_count(run)
            await self._agents.update_run_status(
                run, status=AgentRunStatus.REJECTED, completed=True
            )

        return run

    async def _run_loop(self, run: AgentRun, *, user_role: MembershipRole) -> None:
        tools = _available_tools(user_role)

        while True:
            elapsed_seconds = (datetime.now(UTC) - run.started_at).total_seconds()
            if run.step_count >= run.max_steps:
                await self._agents.update_run_status(
                    run,
                    status=AgentRunStatus.FAILED,
                    error_message=f"Maximum step count ({run.max_steps}) exceeded.",
                    completed=True,
                )
                return
            if elapsed_seconds >= run.max_runtime_seconds:
                await self._agents.update_run_status(
                    run,
                    status=AgentRunStatus.FAILED,
                    error_message=f"Maximum runtime ({run.max_runtime_seconds}s) exceeded.",
                    completed=True,
                )
                return

            transcript = _build_transcript(run)
            try:
                action = await plan_next_action(
                    self._llm_provider,
                    goal=run.goal,
                    tools=tools,
                    transcript=transcript,
                    max_tokens=self._settings.agent_planner_max_tokens,
                )
            except PlannerParseError as exc:
                await self._agents.update_run_status(
                    run,
                    status=AgentRunStatus.FAILED,
                    error_message=(
                        f"Planner returned an unparseable response: {exc.raw_response[:200]}"
                    ),
                    completed=True,
                )
                return
            except Exception as exc:  # noqa: BLE001 - an LLM/network failure must not crash the request
                await self._agents.update_run_status(
                    run,
                    status=AgentRunStatus.FAILED,
                    error_message=f"Planner call failed: {exc}",
                    completed=True,
                )
                return

            raw_action_json = _action_to_json(action)
            await self._agents.add_step(
                run,
                step_index=run.step_count,
                state=AgentStepState.PLANNING,
                reasoning=action.reasoning,
                raw_action_json=raw_action_json,
            )
            await self._agents.increment_step_count(run)

            if isinstance(action, FinalAnswerAction):
                await self._agents.update_run_status(
                    run,
                    status=AgentRunStatus.COMPLETED,
                    final_answer=action.answer,
                    completed=True,
                )
                return

            # ToolCallAction from here on.
            outcome = await self._handle_tool_call_action(run, action, tools, user_role)
            if outcome == "stop":
                return
            # otherwise "continue" — loop back to PLANNING

    async def _handle_tool_call_action(
        self,
        run: AgentRun,
        action: ToolCallAction,
        tools: list[Tool[Any]],
        user_role: MembershipRole,
    ) -> str:
        tool = get_tool(action.tool)
        allowed_names = {t.name for t in tools}

        if tool is None:
            tool_call = await self._agents.add_tool_call(
                run,
                tool_name=action.tool,
                risk_level=ToolRiskLevel.LOW,
                input_data=action.arguments,
            )
            await self._agents.mark_tool_call_failed(
                tool_call, error_message=f"Unknown tool '{action.tool}'."
            )
            await self._record_observation(run, tool_call, f"Tool '{action.tool}' does not exist.")
            return "continue"

        if tool.name not in allowed_names:
            tool_call = await self._agents.add_tool_call(
                run,
                tool_name=tool.name,
                risk_level=tool.risk_level,
                input_data=action.arguments,
            )
            await self._agents.mark_tool_call_failed(
                tool_call,
                error_message="The initiating user's role does not permit using this tool.",
            )
            await self._record_observation(
                run, tool_call, "Permission denied: this tool is not available to your role."
            )
            return "continue"

        executed_count = sum(1 for tc in run.tool_calls if tc.status == ToolCallStatus.EXECUTED)
        if executed_count >= run.max_tool_calls:
            await self._agents.update_run_status(
                run,
                status=AgentRunStatus.FAILED,
                error_message=f"Maximum tool call count ({run.max_tool_calls}) exceeded.",
                completed=True,
            )
            return "stop"

        tool_call = await self._agents.add_tool_call(
            run,
            tool_name=tool.name,
            risk_level=tool.risk_level,
            input_data=action.arguments,
        )

        if tool.risk_level == ToolRiskLevel.HIGH:
            await self._agents.mark_tool_call_awaiting_approval(tool_call)
            await self._agents.update_run_status(run, status=AgentRunStatus.AWAITING_APPROVAL)
            return "stop"

        await self._execute_tool_call(run, tool, tool_call, user_role)
        return "continue"

    async def _execute_tool_call(
        self, run: AgentRun, tool: Tool[Any], tool_call: ToolCall, user_role: MembershipRole
    ) -> None:
        context = ToolExecutionContext(
            session=self._session,
            organization_id=run.organization_id,
            user_id=run.created_by_user_id,
            user_role=user_role,
            search_service=self._search_service,
            document_service=self._document_service,
        )
        result = await tool.run(arguments=tool_call.input_data, context=context)

        if result.success:
            await self._agents.mark_tool_call_executed(tool_call, output_data=result.output)
            await self._record_observation(run, tool_call, _summarize_output(result.output))
        else:
            await self._agents.mark_tool_call_failed(
                tool_call, error_message=result.error or "Tool execution failed."
            )
            await self._record_observation(run, tool_call, f"Error: {result.error}")

    async def _record_observation(self, run: AgentRun, tool_call: ToolCall, summary: str) -> None:
        await self._agents.add_step(
            run,
            step_index=run.step_count,
            state=AgentStepState.OBSERVATION,
            reasoning=summary,
            tool_call_id=tool_call.id,
        )
        await self._agents.increment_step_count(run)


def _action_to_json(action: ToolCallAction | FinalAnswerAction) -> dict[str, Any]:
    if isinstance(action, ToolCallAction):
        return {
            "action": "tool_call",
            "tool": action.tool,
            "arguments": action.arguments,
            "reasoning": action.reasoning,
        }
    return {"action": "final_answer", "answer": action.answer, "reasoning": action.reasoning}


def _summarize_output(output: dict[str, Any]) -> str:
    text = str(output)
    return text[:1000]


def _build_transcript(run: AgentRun) -> list[LLMMessage]:
    """Reconstructs the planner's conversation history from persisted
    AgentStep/ToolCall records — see ADR-012 and AgentStep's docstring for
    why this replays exact stored JSON/output rather than inferring pairing.
    """
    messages: list[LLMMessage] = []
    tool_calls_by_id = {tc.id: tc for tc in run.tool_calls}

    for step in sorted(run.steps, key=lambda s: s.step_index):
        if step.state == AgentStepState.PLANNING and step.raw_action_json is not None:
            messages.append(LLMMessage(role="assistant", content=json.dumps(step.raw_action_json)))
        elif step.state == AgentStepState.OBSERVATION:
            tool_call = tool_calls_by_id.get(step.tool_call_id) if step.tool_call_id else None
            if tool_call is not None:
                content = (
                    f"Tool '{tool_call.tool_name}' result: {step.reasoning}"
                    if tool_call.status == ToolCallStatus.EXECUTED
                    else f"Tool '{tool_call.tool_name}' failed: {step.reasoning}"
                )
            else:
                content = step.reasoning
            messages.append(LLMMessage(role="user", content=content))

    return messages

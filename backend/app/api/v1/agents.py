import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentMembership
from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit_by_user
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.membership import Membership
from app.schemas.agent import (
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunResponse,
    AgentStepResponse,
    ApprovalDecisionRequest,
    ApprovalResponse,
    StartAgentRunRequest,
    ToolCallResponse,
)
from app.services.agents.agent_service import (
    AgentRunNotFoundError,
    AgentService,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    ApprovalPermissionDeniedError,
)
from app.services.document_service import DocumentService
from app.services.embeddings.factory import get_embedding_provider
from app.services.embeddings.provider import EmbeddingProvider
from app.services.llm.factory import get_llm_provider
from app.services.llm.provider import LLMProvider
from app.services.reranking.factory import get_reranker
from app.services.reranking.reranker import Reranker
from app.services.search_service import SearchService
from app.services.storage import get_file_storage

router = APIRouter()

_settings_at_import = get_settings()
_agent_run_rate_limit = rate_limit_by_user(
    "agent-run", limit=_settings_at_import.rate_limit_agent_run_per_hour, window_seconds=3600
)


def _get_agent_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> AgentService:
    search_service = SearchService(db, settings, embedding_provider, reranker)
    document_service = DocumentService(db, settings, get_file_storage())
    return AgentService(db, settings, llm_provider, search_service, document_service)


def _run_to_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        goal=run.goal,
        status=run.status,
        step_count=run.step_count,
        max_steps=run.max_steps,
        final_answer=run.final_answer,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _run_to_detail_response(run: AgentRun) -> AgentRunDetailResponse:
    base = _run_to_response(run)
    return AgentRunDetailResponse(
        **base.model_dump(),
        steps=[
            AgentStepResponse(
                step_index=s.step_index,
                state=s.state,
                reasoning=s.reasoning,
                created_at=s.created_at,
            )
            for s in sorted(run.steps, key=lambda s: s.step_index)
        ],
        tool_calls=[
            ToolCallResponse(
                id=tc.id,
                tool_name=tc.tool_name,
                risk_level=tc.risk_level,
                input_data=tc.input_data,
                output_data=tc.output_data,
                status=tc.status,
                error_message=tc.error_message,
                approval=(
                    ApprovalResponse(
                        id=tc.approval.id,
                        status=tc.approval.status,
                        requested_at=tc.approval.requested_at,
                        decided_at=tc.approval.decided_at,
                        notes=tc.approval.notes,
                    )
                    if tc.approval is not None
                    else None
                ),
            )
            for tc in sorted(run.tool_calls, key=lambda tc: tc.created_at)
        ],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentRunDetailResponse,
    dependencies=[Depends(_agent_run_rate_limit)],
)
async def start_agent_run(
    body: StartAgentRunRequest,
    membership: CurrentMembership,
    agent_service: Annotated[AgentService, Depends(_get_agent_service)],
) -> AgentRunDetailResponse:
    run = await agent_service.start_run(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        user_role=membership.role,
        goal=body.goal,
    )
    # Re-fetch with eager-loaded steps/tool_calls/approvals for the response
    # — the object start_run returns may not have those relationships
    # populated depending on how far the loop progressed.
    detailed_run = await agent_service.get_run(
        organization_id=membership.organization_id, run_id=run.id
    )
    return _run_to_detail_response(detailed_run)


@router.get("", response_model=AgentRunListResponse)
async def list_agent_runs(
    membership: CurrentMembership,
    agent_service: Annotated[AgentService, Depends(_get_agent_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentRunListResponse:
    items, total = await agent_service.list_runs(
        organization_id=membership.organization_id, limit=limit, offset=offset
    )
    return AgentRunListResponse(
        items=[_run_to_response(r) for r in items], total=total, limit=limit, offset=offset
    )


@router.get("/{run_id}", response_model=AgentRunDetailResponse)
async def get_agent_run(
    run_id: uuid.UUID,
    membership: CurrentMembership,
    agent_service: Annotated[AgentService, Depends(_get_agent_service)],
) -> AgentRunDetailResponse:
    try:
        run = await agent_service.get_run(organization_id=membership.organization_id, run_id=run_id)
    except AgentRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found."
        ) from exc
    return _run_to_detail_response(run)


@router.post("/approvals/{approval_id}/approve", response_model=AgentRunDetailResponse)
async def approve_tool_call(
    approval_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    membership: CurrentMembership,
    agent_service: Annotated[AgentService, Depends(_get_agent_service)],
) -> AgentRunDetailResponse:
    run = await _decide(agent_service, approval_id, True, membership, body.notes)
    return _run_to_detail_response(run)


@router.post("/approvals/{approval_id}/reject", response_model=AgentRunDetailResponse)
async def reject_tool_call(
    approval_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    membership: CurrentMembership,
    agent_service: Annotated[AgentService, Depends(_get_agent_service)],
) -> AgentRunDetailResponse:
    run = await _decide(agent_service, approval_id, False, membership, body.notes)
    return _run_to_detail_response(run)


async def _decide(
    agent_service: AgentService,
    approval_id: uuid.UUID,
    approved: bool,
    membership: Membership,
    notes: str | None,
) -> AgentRun:
    try:
        return await agent_service.decide_approval(
            organization_id=membership.organization_id,
            approval_id=approval_id,
            approved=approved,
            decided_by_user_id=membership.user_id,
            user_role=membership.role,
            notes=notes,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found."
        ) from exc
    except ApprovalAlreadyDecidedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This approval has already been decided."
        ) from exc
    except ApprovalPermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

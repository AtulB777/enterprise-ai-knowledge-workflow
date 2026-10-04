"""Orchestrates an evaluation run: ensures the golden dataset is ingested
through the real pipeline, runs each golden case through real hybrid search
and RAG generation, computes metrics, persists results, and compares against
the previous run for regression detection (spec §28).
"""

import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.pricing import estimate_cost_usd
from app.core.security import hash_password
from app.models.document import DocumentStatus
from app.models.membership import MembershipRole
from app.models.organization import Organization
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.services.conversation_service import ConversationService
from app.services.document_service import DocumentService
from app.services.embeddings.provider import EmbeddingProvider
from app.services.llm.provider import LLMProvider
from app.services.rag_service import RagService
from app.services.reranking.reranker import Reranker
from app.services.search_service import SearchService
from app.services.storage import FileStorage
from app.workers.tasks import process_document
from evaluation.generation_metrics import (
    JudgeParseError,
    citation_precision,
    citation_recall,
    judge_faithfulness_and_relevance,
)
from evaluation.golden_dataset import DATASET_VERSION, GOLDEN_CASES, GOLDEN_DOCUMENTS, GoldenCase
from evaluation.retrieval_metrics import (
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

logger = logging.getLogger("evaluation")

_EVAL_ORG_NAME = "Evaluation Dataset"
_EVAL_USER_EMAIL = "evaluation@internal.example"
_REGRESSION_THRESHOLD = 0.05  # 5 percentage points


@dataclass
class CaseOutcome:
    case_id: str
    query: str
    metrics: dict[str, float]
    latency_ms: float
    error: str | None = None


@dataclass
class EvaluationReport:
    run_id: uuid.UUID
    dataset_version: str
    case_outcomes: list[CaseOutcome]
    summary_metrics: dict[str, float]
    baseline_summary_metrics: dict[str, float] | None = None
    regressions: list[str] = field(default_factory=list)


class EvaluationRunner:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        reranker: Reranker,
        llm_provider: LLMProvider,
        storage: FileStorage,
        *,
        run_llm_judge: bool = False,
    ) -> None:
        self._session = session
        self._settings = settings
        self._embedding_provider = embedding_provider
        self._reranker = reranker
        self._llm_provider = llm_provider
        self._storage = storage
        self._run_llm_judge = run_llm_judge
        self._evaluations = EvaluationRepository(session)

    async def run(self) -> EvaluationReport:
        organization, user = await self._get_or_create_eval_context()
        document_id_by_filename = await self._ensure_golden_documents_ingested(
            organization.id, user.id
        )

        eval_run = await self._evaluations.create_run(
            organization_id=organization.id, dataset_version=DATASET_VERSION
        )

        search_service = SearchService(
            self._session, self._settings, self._embedding_provider, self._reranker
        )
        rag_service = RagService(self._session, self._settings, search_service, self._llm_provider)
        conversation_service = ConversationService(self._session)
        conversation = await conversation_service.create_conversation(
            organization_id=organization.id, created_by_user_id=user.id
        )

        outcomes: list[CaseOutcome] = []
        try:
            for case in GOLDEN_CASES:
                outcome = await self._evaluate_case(
                    case,
                    organization_id=organization.id,
                    conversation_id=conversation.id,
                    document_id_by_filename=document_id_by_filename,
                    search_service=search_service,
                    rag_service=rag_service,
                )
                outcomes.append(outcome)
                await self._evaluations.add_result(
                    run_id=eval_run.id,
                    case_id=outcome.case_id,
                    query=outcome.query,
                    metrics=outcome.metrics,
                    latency_ms=outcome.latency_ms,
                    error_message=outcome.error,
                )

            summary = _aggregate_metrics(outcomes)
            await self._evaluations.complete_run(eval_run, summary_metrics=summary)
        except Exception as exc:
            await self._evaluations.fail_run(eval_run, error_message=str(exc))
            raise

        baseline = await self._evaluations.get_previous_completed_run(
            organization_id=organization.id,
            dataset_version=DATASET_VERSION,
            before_run_id=eval_run.id,
        )
        regressions: list[str] = []
        baseline_summary = None
        if baseline is not None:
            baseline_summary = baseline.summary_metrics
            regressions = _detect_regressions(baseline_summary, summary)

        return EvaluationReport(
            run_id=eval_run.id,
            dataset_version=DATASET_VERSION,
            case_outcomes=outcomes,
            summary_metrics=summary,
            baseline_summary_metrics=baseline_summary,
            regressions=regressions,
        )

    async def _get_or_create_eval_context(self) -> tuple[Organization, User]:
        org_repo = OrganizationRepository(self._session)
        user_repo = UserRepository(self._session)
        membership_repo = MembershipRepository(self._session)

        organization = await org_repo.get_by_slug("evaluation-dataset")
        if organization is None:
            organization = await org_repo.create_with_unique_slug(name=_EVAL_ORG_NAME)

        user = await user_repo.get_by_email(_EVAL_USER_EMAIL)
        if user is None:
            user = await user_repo.create(
                email=_EVAL_USER_EMAIL,
                # Random, never used to log in — this account exists only
                # so the eval runner has a valid uploaded_by/created_by
                # identity, going through the same real service layer as a
                # normal user rather than bypassing it with null FKs.
                hashed_password=hash_password(secrets.token_urlsafe(32)),
                full_name="Evaluation Runner",
            )
            await membership_repo.create(
                user_id=user.id, organization_id=organization.id, role=MembershipRole.ADMIN
            )

        await self._session.commit()
        return organization, user

    async def _ensure_golden_documents_ingested(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, uuid.UUID]:
        document_service = DocumentService(self._session, self._settings, self._storage)
        document_repo = DocumentRepository(self._session)

        existing_documents, _ = await document_repo.list_for_org(
            organization_id=organization_id, collection_id=None, limit=100, offset=0
        )
        existing_by_filename = {d.original_filename: d for d in existing_documents}

        document_id_by_filename: dict[str, uuid.UUID] = {}
        for golden_doc in GOLDEN_DOCUMENTS:
            existing = existing_by_filename.get(golden_doc.filename)
            if existing is not None and existing.status == DocumentStatus.COMPLETED:
                document_id_by_filename[golden_doc.filename] = existing.id
                continue

            document = await document_service.upload_document(
                organization_id=organization_id,
                uploaded_by_user_id=user_id,
                collection_id=None,
                filename=golden_doc.filename,
                content=golden_doc.content.encode("utf-8"),
            )
            # Process synchronously here (not via the arq queue) so the
            # golden dataset is guaranteed fully indexed before evaluation
            # starts — a CLI tool shouldn't have to poll a background worker
            # to get reproducible, immediate results.
            await process_document(
                ctx={},
                document_id=str(document.id),
                embedding_provider=self._embedding_provider,
            )
            document_id_by_filename[golden_doc.filename] = document.id

        return document_id_by_filename

    async def _evaluate_case(
        self,
        case: GoldenCase,
        *,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        document_id_by_filename: dict[str, uuid.UUID],
        search_service: SearchService,
        rag_service: RagService,
    ) -> CaseOutcome:
        start = time.perf_counter()
        try:
            search_results = await search_service.search(
                organization_id=organization_id, query=case.query
            )
            retrieved_filenames = _dedupe_preserve_order(
                [r.document_filename for r in search_results]
            )
            relevant_filenames = set(case.relevant_filenames)

            metrics: dict[str, float] = {
                "recall_at_5": recall_at_k(retrieved_filenames, relevant_filenames, k=5),
                "precision_at_5": precision_at_k(retrieved_filenames, relevant_filenames, k=5),
                "mrr": mean_reciprocal_rank(retrieved_filenames, relevant_filenames),
                "ndcg_at_5": ndcg_at_k(retrieved_filenames, relevant_filenames, k=5),
            }

            answer = await rag_service.ask(
                organization_id=organization_id,
                conversation_id=conversation_id,
                question=case.query,
            )
            cited_document_ids = {str(c.document_id) for c in answer.citations}
            relevant_document_ids = {
                str(document_id_by_filename[f])
                for f in relevant_filenames
                if f in document_id_by_filename
            }
            metrics["citation_precision"] = citation_precision(
                cited_document_ids, relevant_document_ids
            )
            metrics["citation_recall"] = citation_recall(cited_document_ids, relevant_document_ids)

            if answer.input_tokens is not None and answer.output_tokens is not None:
                metrics["input_tokens"] = float(answer.input_tokens)
                metrics["output_tokens"] = float(answer.output_tokens)
                metrics["estimated_cost_usd"] = estimate_cost_usd(
                    model=answer.model or "",
                    input_tokens=answer.input_tokens,
                    output_tokens=answer.output_tokens,
                )

            if self._run_llm_judge:
                try:
                    context_text = "\n\n".join(r.chunk.content for r in search_results)
                    judge_scores = await judge_faithfulness_and_relevance(
                        self._llm_provider,
                        question=case.query,
                        context=context_text,
                        answer=answer.message.content,
                    )
                    metrics.update(judge_scores)
                except JudgeParseError as exc:
                    logger.warning("Judge response unparseable for case %s: %s", case.case_id, exc)

            latency_ms = (time.perf_counter() - start) * 1000
            return CaseOutcome(
                case_id=case.case_id, query=case.query, metrics=metrics, latency_ms=latency_ms
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Case %s failed: %s", case.case_id, exc)
            return CaseOutcome(
                case_id=case.case_id,
                query=case.query,
                metrics={},
                latency_ms=latency_ms,
                error=str(exc),
            )


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _aggregate_metrics(outcomes: list[CaseOutcome]) -> dict[str, float]:
    successful = [o for o in outcomes if o.error is None]
    metric_names: set[str] = set()
    for o in successful:
        metric_names.update(o.metrics.keys())

    summary: dict[str, float] = {}
    for name in sorted(metric_names):
        values = [o.metrics[name] for o in successful if name in o.metrics]
        if values:
            summary[name] = sum(values) / len(values)

    summary["error_rate"] = (
        sum(1 for o in outcomes if o.error is not None) / len(outcomes) if outcomes else 0.0
    )
    summary["avg_latency_ms"] = (
        sum(o.latency_ms for o in outcomes) / len(outcomes) if outcomes else 0.0
    )
    return summary


def _detect_regressions(
    baseline: dict[str, Any], current: dict[str, float], threshold: float = _REGRESSION_THRESHOLD
) -> list[str]:
    regressions = []
    for metric_name, current_value in current.items():
        if metric_name in ("error_rate", "avg_latency_ms"):
            continue
        baseline_value = baseline.get(metric_name)
        if baseline_value is None:
            continue
        if current_value < baseline_value - threshold:
            regressions.append(
                f"{metric_name}: {baseline_value:.3f} -> {current_value:.3f} "
                f"(dropped {baseline_value - current_value:.3f})"
            )

    if "error_rate" in current and "error_rate" in baseline:
        if current["error_rate"] > baseline["error_rate"] + threshold:
            regressions.append(
                f"error_rate: {baseline['error_rate']:.3f} -> "
                f"{current['error_rate']:.3f} (increased)"
            )
    return regressions

"""Integration tests for the evaluation runner against real Postgres,
proving the entire harness (golden dataset ingestion, real hybrid search,
real RAG generation, metric computation, persistence, baseline comparison)
works end-to-end — with fake embedding/reranking/LLM providers injected,
same as every pipeline test since Phase 5 (see ADR-011).
"""

from sqlalchemy import select

from app.core.config import get_settings
from app.models.evaluation import EvaluationRun, EvaluationRunStatus
from app.services.storage import LocalFileStorage
from evaluation.golden_dataset import GOLDEN_CASES, GOLDEN_DOCUMENTS
from evaluation.retrieval_metrics import precision_at_k
from evaluation.runner import EvaluationRunner
from tests.fakes import FakeEmbeddingProvider, FakeLLMProvider, FakeReranker


async def _build_runner(db_session, *, run_llm_judge: bool = False) -> EvaluationRunner:
    settings = get_settings()
    assert settings.storage_root is not None
    storage = LocalFileStorage(settings.storage_root)
    return EvaluationRunner(
        db_session,
        settings,
        FakeEmbeddingProvider(),
        FakeReranker(),
        FakeLLMProvider(),
        storage,
        run_llm_judge=run_llm_judge,
    )


async def test_runner_completes_and_evaluates_all_golden_cases(db_session) -> None:
    runner = await _build_runner(db_session)

    report = await runner.run()

    assert report.dataset_version == "v1"
    assert len(report.case_outcomes) == len(GOLDEN_CASES)
    assert all(outcome.error is None for outcome in report.case_outcomes)
    assert "recall_at_5" in report.summary_metrics
    assert "citation_precision" in report.summary_metrics
    assert "error_rate" in report.summary_metrics
    assert report.summary_metrics["error_rate"] == 0.0


async def test_runner_persists_run_and_results(db_session) -> None:
    runner = await _build_runner(db_session)
    report = await runner.run()

    result = await db_session.execute(
        select(EvaluationRun).where(EvaluationRun.id == report.run_id)
    )
    run = result.scalar_one()
    assert run.status == EvaluationRunStatus.COMPLETED
    assert run.completed_at is not None


async def test_runner_gets_perfect_retrieval_for_exact_match_case(db_session) -> None:
    """The 'vacation-days' golden case's query shares heavy vocabulary with
    its one relevant document — real Postgres full-text search alone should
    find it, confirming the retrieval half of the pipeline genuinely works,
    not just that the harness runs without crashing.
    """
    runner = await _build_runner(db_session)
    report = await runner.run()

    vacation_case = next(o for o in report.case_outcomes if o.case_id == "vacation-days")
    assert vacation_case.metrics["recall_at_5"] == 1.0


async def test_runner_second_run_is_idempotent_on_ingestion(db_session) -> None:
    runner1 = await _build_runner(db_session)
    await runner1.run()

    runner2 = await _build_runner(db_session)
    report2 = await runner2.run()

    assert all(outcome.error is None for outcome in report2.case_outcomes)


async def test_second_run_uses_first_as_baseline(db_session) -> None:
    runner1 = await _build_runner(db_session)
    report1 = await runner1.run()

    runner2 = await _build_runner(db_session)
    report2 = await runner2.run()

    assert report2.baseline_summary_metrics is not None
    assert report2.baseline_summary_metrics == report1.summary_metrics
    # Identical inputs/providers -> identical scores -> no regressions.
    assert report2.regressions == []


def test_unrelated_query_correctly_scores_zero_precision() -> None:
    # Sanity check on the golden dataset's own design: the "unrelated-topic"
    # case has zero relevant documents, so nothing retrieved can be a true
    # positive.
    case = next(c for c in GOLDEN_CASES if c.case_id == "unrelated-topic")
    assert case.relevant_filenames == frozenset()
    assert precision_at_k(["anything", "at", "all"], set(case.relevant_filenames), k=3) == 0.0


def test_golden_dataset_cases_reference_real_documents() -> None:
    """Every relevant_filenames entry in every case must actually exist in
    GOLDEN_DOCUMENTS — a typo here would silently make a case unwinnable.
    """
    document_filenames = {d.filename for d in GOLDEN_DOCUMENTS}
    for case in GOLDEN_CASES:
        assert (
            case.relevant_filenames <= document_filenames
        ), f"case {case.case_id} references a filename not in GOLDEN_DOCUMENTS"


async def test_runner_records_token_usage_and_cost_per_case(db_session) -> None:
    """Real proof that RagAnswer's token/model fields (added alongside the
    MODEL_COST metric work) actually flow through to per-case evaluation
    metrics, not just that the fields exist on the dataclass.
    """
    runner = await _build_runner(db_session)

    report = await runner.run()

    cases_with_a_real_answer = [
        o for o in report.case_outcomes if o.error is None and "recall_at_5" in o.metrics
    ]
    assert cases_with_a_real_answer, "expected at least one case to reach the LLM call"
    for outcome in cases_with_a_real_answer:
        # FakeLLMProvider reports input_tokens=10, output_tokens=10 (see tests/fakes.py).
        assert outcome.metrics["input_tokens"] == 10.0
        assert outcome.metrics["output_tokens"] == 10.0
        # "fake-llm-test-only" isn't in app/core/pricing.py's table, so the
        # estimate is legitimately zero — same expected behavior as
        # test_pricing.py's unknown-model case, not a bug.
        assert outcome.metrics["estimated_cost_usd"] == 0.0

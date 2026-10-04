"""CLI entrypoint: `python -m evaluation.run`

Runs the evaluation harness against real Postgres/pgvector using whichever
providers are configured (app/services/*/factory.py — same factories the
running application uses). See ADR-011 for what this can and can't verify
without a real embedding model / LLM API key available.
"""

import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.embeddings.factory import get_embedding_provider
from app.services.llm.factory import get_llm_provider
from app.services.reranking.factory import get_reranker
from app.services.storage import get_file_storage
from evaluation.runner import EvaluationReport, EvaluationRunner


def _print_report(report: EvaluationReport) -> None:
    print(f"\n{'=' * 60}")
    print(f"Evaluation run {report.run_id}  (dataset {report.dataset_version})")
    print(f"{'=' * 60}\n")

    print(f"{'Case':<28} {'Status':<10} {'Latency (ms)':>12}")
    print("-" * 52)
    for outcome in report.case_outcomes:
        status = "ERROR" if outcome.error else "ok"
        print(f"{outcome.case_id:<28} {status:<10} {outcome.latency_ms:>12.1f}")
        if outcome.error:
            print(f"    -> {outcome.error}")

    print(f"\n{'Summary metrics':<28}")
    print("-" * 52)
    for name, value in sorted(report.summary_metrics.items()):
        line = f"{name:<28} {value:.3f}"
        if report.baseline_summary_metrics and name in report.baseline_summary_metrics:
            delta = value - report.baseline_summary_metrics[name]
            line += f"   (baseline {report.baseline_summary_metrics[name]:.3f}, delta {delta:+.3f})"
        print(line)

    if report.regressions:
        print(f"\n{'!' * 60}")
        print("REGRESSIONS DETECTED:")
        for regression in report.regressions:
            print(f"  - {regression}")
        print(f"{'!' * 60}\n")
    else:
        print("\nNo regressions detected against the previous run.\n")


async def _main(run_llm_judge: bool) -> int:
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        runner = EvaluationRunner(
            session,
            settings,
            get_embedding_provider(),
            get_reranker(),
            get_llm_provider(),
            get_file_storage(),
            run_llm_judge=run_llm_judge,
        )
        report = await runner.run()

    _print_report(report)
    return 1 if report.regressions else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the RAG evaluation suite.")
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Also run LLM-as-judge faithfulness/relevance scoring (needs a working LLM provider).",
    )
    args = parser.parse_args()
    exit_code = asyncio.run(_main(args.llm_judge))
    sys.exit(exit_code)

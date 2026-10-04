"""Agent-quality metrics (spec §27's second metric list: task success rate,
tool selection accuracy, unnecessary tool calls). Pure functions — no DB, no
LLM — operating on a simple outcome record extracted from a real AgentRun.
Same pattern as retrieval_metrics.py: correctness is verified in tests
against hand-worked examples, not just "the code runs."

Scope note (see ADR-013, finding 5): spec §27 lists six agent metrics this
covers three of (task success rate, tool selection accuracy, unnecessary
tool calls). "Tool argument correctness" is largely already enforced by
Tool.run()'s Pydantic input validation (Phase 9) rather than a separate
after-the-fact metric; "failure recovery" and a completion-rate metric
distinct from success rate are deliberately deferred, not silently dropped
— tracked in PLAN.md as a scoped-out follow-up.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRunOutcome:
    """What's measured from one real AgentRun, extracted by the caller —
    this module never touches the DB or AgentService itself, keeping the
    metric functions independently testable with synthetic data.
    """

    case_id: str
    completed: bool  # AgentRunStatus.COMPLETED specifically, not just terminal
    tool_names_used: list[str]  # in the order they were actually called


def task_success_rate(outcomes: list[AgentRunOutcome]) -> float:
    """Fraction of runs that reached COMPLETED (not FAILED/REJECTED/stuck
    AWAITING_APPROVAL). 0.0 for an empty outcome list — no runs to succeed.
    """
    if not outcomes:
        return 0.0
    return sum(1 for o in outcomes if o.completed) / len(outcomes)


def tool_selection_accuracy(outcome: AgentRunOutcome, acceptable_tools: frozenset[str]) -> float:
    """Fraction of the tools actually used that were within the task's
    acceptable set. Vacuously 1.0 if no tools were used at all — an agent
    that called zero tools can't have chosen the wrong ones; a task that
    needed tools but got none is a task_success_rate problem, not a
    selection-accuracy one.
    """
    if not outcome.tool_names_used:
        return 1.0
    acceptable_uses = sum(1 for name in outcome.tool_names_used if name in acceptable_tools)
    return acceptable_uses / len(outcome.tool_names_used)


def unnecessary_tool_calls(outcome: AgentRunOutcome, minimum_tool_calls: int) -> int:
    """How many more tool calls were made than the task's known minimum.
    Never negative — using fewer calls than the minimum (e.g. because the
    run failed before finishing) is a task_success_rate problem, not
    counted here as a negative "unnecessary" value.
    """
    return max(0, len(outcome.tool_names_used) - minimum_tool_calls)

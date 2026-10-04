"""Agent-quality metrics verified against hand-worked values — same
verification standard as test_retrieval_metrics.py.
"""

from evaluation.agent_metrics import (
    AgentRunOutcome,
    task_success_rate,
    tool_selection_accuracy,
    unnecessary_tool_calls,
)


def test_task_success_rate_all_completed() -> None:
    outcomes = [
        AgentRunOutcome(case_id="a", completed=True, tool_names_used=["calculate"]),
        AgentRunOutcome(case_id="b", completed=True, tool_names_used=[]),
    ]
    assert task_success_rate(outcomes) == 1.0


def test_task_success_rate_partial() -> None:
    outcomes = [
        AgentRunOutcome(case_id="a", completed=True, tool_names_used=[]),
        AgentRunOutcome(case_id="b", completed=False, tool_names_used=[]),
        AgentRunOutcome(case_id="c", completed=False, tool_names_used=[]),
        AgentRunOutcome(case_id="d", completed=True, tool_names_used=[]),
    ]
    assert task_success_rate(outcomes) == 0.5


def test_task_success_rate_empty_list_is_zero() -> None:
    assert task_success_rate([]) == 0.0


def test_tool_selection_accuracy_all_acceptable() -> None:
    outcome = AgentRunOutcome(
        case_id="a", completed=True, tool_names_used=["calculate", "calculate"]
    )
    assert tool_selection_accuracy(outcome, acceptable_tools=frozenset({"calculate"})) == 1.0


def test_tool_selection_accuracy_partial() -> None:
    outcome = AgentRunOutcome(
        case_id="a",
        completed=True,
        tool_names_used=["search_documents", "delete_document", "search_documents"],
    )
    # 2 of 3 calls were within the acceptable set -> 2/3
    result = tool_selection_accuracy(outcome, acceptable_tools=frozenset({"search_documents"}))
    assert abs(result - (2 / 3)) < 1e-9


def test_tool_selection_accuracy_no_tools_used_is_vacuously_perfect() -> None:
    outcome = AgentRunOutcome(case_id="a", completed=False, tool_names_used=[])
    assert tool_selection_accuracy(outcome, acceptable_tools=frozenset({"calculate"})) == 1.0


def test_tool_selection_accuracy_zero_when_nothing_acceptable_used() -> None:
    outcome = AgentRunOutcome(case_id="a", completed=True, tool_names_used=["delete_document"])
    assert tool_selection_accuracy(outcome, acceptable_tools=frozenset({"calculate"})) == 0.0


def test_unnecessary_tool_calls_none_when_at_minimum() -> None:
    outcome = AgentRunOutcome(case_id="a", completed=True, tool_names_used=["calculate"])
    assert unnecessary_tool_calls(outcome, minimum_tool_calls=1) == 0


def test_unnecessary_tool_calls_counts_the_excess() -> None:
    outcome = AgentRunOutcome(
        case_id="a", completed=True, tool_names_used=["calculate", "calculate", "calculate"]
    )
    assert unnecessary_tool_calls(outcome, minimum_tool_calls=1) == 2


def test_unnecessary_tool_calls_never_negative() -> None:
    outcome = AgentRunOutcome(case_id="a", completed=False, tool_names_used=[])
    assert unnecessary_tool_calls(outcome, minimum_tool_calls=3) == 0

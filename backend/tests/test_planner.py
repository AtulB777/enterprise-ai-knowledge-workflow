"""Planner JSON parsing tests (ADR-012 decision 1) — same rigor as Phase 8's
JudgeParseError tests: malformed output must be a distinct, catchable error,
never a silent misparse or a crash.
"""

import pytest

from app.services.agents.planner import (
    FinalAnswerAction,
    PlannerParseError,
    ToolCallAction,
    build_planner_system_prompt,
    parse_planner_response,
)
from app.services.agents.tools.registry import list_tools


def test_parses_valid_tool_call_action() -> None:
    raw = (
        '{"action": "tool_call", "tool": "calculate", '
        '"arguments": {"expression": "2+2"}, "reasoning": "need math"}'
    )
    action = parse_planner_response(raw)
    assert isinstance(action, ToolCallAction)
    assert action.tool == "calculate"
    assert action.arguments == {"expression": "2+2"}
    assert action.reasoning == "need math"


def test_parses_valid_final_answer_action() -> None:
    raw = '{"action": "final_answer", "answer": "The result is 4.", "reasoning": "computed it"}'
    action = parse_planner_response(raw)
    assert isinstance(action, FinalAnswerAction)
    assert action.answer == "The result is 4."


def test_tool_call_defaults_missing_arguments_to_empty_dict() -> None:
    raw = '{"action": "tool_call", "tool": "search_documents", "reasoning": "look it up"}'
    action = parse_planner_response(raw)
    assert isinstance(action, ToolCallAction)
    assert action.arguments == {}


def test_raises_on_malformed_json() -> None:
    with pytest.raises(PlannerParseError):
        parse_planner_response("I think you should call search_documents.")


def test_raises_on_non_object_json() -> None:
    with pytest.raises(PlannerParseError):
        parse_planner_response("[1, 2, 3]")


def test_raises_on_unknown_action_type() -> None:
    with pytest.raises(PlannerParseError):
        parse_planner_response('{"action": "do_something_else"}')


def test_raises_on_tool_call_missing_tool_name() -> None:
    with pytest.raises(PlannerParseError):
        parse_planner_response('{"action": "tool_call", "arguments": {}}')


def test_raises_on_final_answer_missing_answer() -> None:
    with pytest.raises(PlannerParseError):
        parse_planner_response('{"action": "final_answer", "reasoning": "done"}')


def test_raises_on_missing_action_field() -> None:
    with pytest.raises(PlannerParseError):
        parse_planner_response('{"tool": "calculate"}')


def test_system_prompt_describes_every_registered_tool() -> None:
    tools = list_tools()
    prompt = build_planner_system_prompt(tools)
    for tool in tools:
        assert tool.name in prompt
        assert tool.description in prompt


def test_system_prompt_instructs_json_only_response() -> None:
    prompt = build_planner_system_prompt(list_tools())
    assert "JSON object" in prompt

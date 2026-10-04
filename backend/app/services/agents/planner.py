"""The agent planner (spec §21). Asks the LLM to respond with a JSON action
description and parses it — see ADR-012 decision 1 for why this is JSON
prompting rather than native provider tool-calling.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

from app.services.agents.tools.base import Tool
from app.services.llm.provider import LLMMessage, LLMProvider

_SYSTEM_PROMPT_TEMPLATE = """You are an autonomous agent working on behalf of a user inside an \
enterprise knowledge platform. Your goal is given below. You have access to a fixed set of tools \
— you may ONLY use these, and only in the ways described.

Available tools:
{tool_descriptions}

On every turn, respond with ONLY a single JSON object, nothing else — no prose before or after it.

To call a tool:
{{"action": "tool_call", "tool": "<tool name>", "arguments": {{...}}, "reasoning": "<why this \
tool, this step>"}}

To finish with your answer (only once you have enough information to answer the goal, or once \
you're confident no available tool can help further):
{{"action": "final_answer", "answer": "<your answer to the goal>", "reasoning": "<why you're \
confident this is enough>"}}

Rules:
- Only call tools listed above, with arguments matching their description.
- Do not call the same tool with the same arguments twice in a row.
- If a tool call fails or returns an error, adapt your next step rather than repeating it unchanged.
- Base your final answer only on information tools actually returned to you — never invent data.
"""


@dataclass(frozen=True)
class ToolCallAction:
    tool: str
    arguments: dict[str, Any]
    reasoning: str


@dataclass(frozen=True)
class FinalAnswerAction:
    answer: str
    reasoning: str


PlannerAction = ToolCallAction | FinalAnswerAction


class PlannerParseError(Exception):
    """A real, expected failure mode — same category as Phase 8's
    JudgeParseError. The planner LLM can return unparseable or
    schema-invalid output; callers must treat this as a distinct, catchable
    error, not a crash or a silently-wrong action.
    """

    def __init__(self, raw_response: str) -> None:
        self.raw_response = raw_response
        super().__init__(
            f"Could not parse planner response as a valid action: {raw_response[:200]!r}"
        )


def build_planner_system_prompt(tools: list[Tool[Any]]) -> str:
    tool_descriptions = "\n".join(
        f"- {tool.name} ({tool.risk_level.value} risk): {tool.description}\n"
        f"  Input schema: {tool.input_schema.model_json_schema()}"
        for tool in tools
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=tool_descriptions)


def parse_planner_response(raw_content: str) -> PlannerAction:
    try:
        parsed = json.loads(raw_content.strip())
    except json.JSONDecodeError as exc:
        raise PlannerParseError(raw_content) from exc

    if not isinstance(parsed, dict):
        raise PlannerParseError(raw_content)

    action: Literal["tool_call", "final_answer"] | None = parsed.get("action")
    try:
        if action == "tool_call":
            return ToolCallAction(
                tool=str(parsed["tool"]),
                arguments=dict(parsed.get("arguments") or {}),
                reasoning=str(parsed.get("reasoning", "")),
            )
        if action == "final_answer":
            return FinalAnswerAction(
                answer=str(parsed["answer"]),
                reasoning=str(parsed.get("reasoning", "")),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise PlannerParseError(raw_content) from exc

    raise PlannerParseError(raw_content)


async def plan_next_action(
    llm_provider: LLMProvider,
    *,
    goal: str,
    tools: list[Tool[Any]],
    transcript: list[LLMMessage],
    max_tokens: int,
) -> PlannerAction:
    system_prompt = build_planner_system_prompt(tools)
    messages = [LLMMessage(role="user", content=f"Goal: {goal}"), *transcript]
    response = await llm_provider.complete(
        system=system_prompt, messages=messages, max_tokens=max_tokens
    )
    return parse_planner_response(response.content)

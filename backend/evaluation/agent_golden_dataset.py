"""Golden dataset for agent-quality metrics (spec §27's second metric list).
Parallels evaluation/golden_dataset.py's RAG dataset — small, versioned,
reviewable as a plain-data diff.
"""

from dataclasses import dataclass

AGENT_DATASET_VERSION = "v1"


@dataclass(frozen=True)
class AgentTaskCase:
    case_id: str
    goal: str
    # Tool names acceptable for this task — using anything outside this set
    # counts against tool_selection_accuracy, even if the run still completes.
    acceptable_tools: frozenset[str]
    # The fewest tool calls genuinely needed to accomplish the goal — used to
    # compute unnecessary_tool_calls (calls beyond this minimum).
    minimum_tool_calls: int


AGENT_GOLDEN_CASES: list[AgentTaskCase] = [
    AgentTaskCase(
        case_id="simple-calculation",
        goal="What is 15 times 3?",
        acceptable_tools=frozenset({"calculate"}),
        minimum_tool_calls=1,
    ),
    AgentTaskCase(
        case_id="document-lookup",
        goal="What does our vacation policy say about days per year?",
        acceptable_tools=frozenset({"search_documents", "get_document"}),
        minimum_tool_calls=1,
    ),
    AgentTaskCase(
        case_id="report-generation",
        goal="Generate a short report summarizing our remote work policy.",
        acceptable_tools=frozenset({"generate_report", "search_documents"}),
        minimum_tool_calls=1,
    ),
]

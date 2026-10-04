"""Generation quality metrics (spec §27): citation correctness is
deterministic (set comparison against golden-dataset ground truth).
Faithfulness and answer relevance are inherently semantic judgments and use
an LLM-as-judge — see ADR-011 for why, and for the honest limits on what
can be verified without a real API key in this sandbox.
"""

import json

from app.services.llm.provider import LLMMessage, LLMProvider


def citation_precision(cited_document_ids: set[str], relevant_document_ids: set[str]) -> float:
    """Of the documents actually cited, what fraction were truly relevant?"""
    if not cited_document_ids:
        return 0.0
    return len(cited_document_ids & relevant_document_ids) / len(cited_document_ids)


def citation_recall(cited_document_ids: set[str], relevant_document_ids: set[str]) -> float:
    """Of the truly relevant documents, what fraction did the answer cite?"""
    if not relevant_document_ids:
        return 1.0
    return len(cited_document_ids & relevant_document_ids) / len(relevant_document_ids)


_JUDGE_SYSTEM_PROMPT = """You are an evaluation judge for a RAG (retrieval-augmented generation) \
system. You will be given a question, the retrieved context the system had available, and the \
answer it produced. Score the answer on two dimensions, each from 0.0 to 1.0:

- "faithfulness": does the answer ONLY state things that are actually supported by the provided \
context? 1.0 means every claim is grounded in the context; 0.0 means the answer contains \
fabricated or unsupported claims.
- "relevance": does the answer actually address the question asked? 1.0 means fully relevant; \
0.0 means it doesn't address the question at all.

Respond with ONLY a JSON object in this exact form, nothing else:
{"faithfulness": <float>, "relevance": <float>, "reasoning": "<one sentence>"}
"""


class JudgeParseError(Exception):
    """A real, expected failure mode for any LLM-judge harness — the judge
    model can return unparseable output. Callers catch this and record it as
    a per-case error rather than letting one bad judge response crash an
    entire evaluation run.
    """

    def __init__(self, raw_response: str) -> None:
        self.raw_response = raw_response
        super().__init__(f"Could not parse judge response as valid JSON: {raw_response[:200]!r}")


async def judge_faithfulness_and_relevance(
    llm_provider: LLMProvider,
    *,
    question: str,
    context: str,
    answer: str,
) -> dict[str, float]:
    user_content = (
        f"<question>\n{question}\n</question>\n\n"
        f"<context>\n{context}\n</context>\n\n"
        f"<answer>\n{answer}\n</answer>"
    )
    response = await llm_provider.complete(
        system=_JUDGE_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_content)],
        max_tokens=200,
    )

    try:
        parsed = json.loads(response.content.strip())
        faithfulness = float(parsed["faithfulness"])
        relevance = float(parsed["relevance"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise JudgeParseError(response.content) from exc

    # Defensive clamping: a misbehaving judge could return an out-of-range
    # value (e.g. "1.2") — never let that silently corrupt aggregate stats.
    return {
        "faithfulness": max(0.0, min(1.0, faithfulness)),
        "relevance": max(0.0, min(1.0, relevance)),
    }

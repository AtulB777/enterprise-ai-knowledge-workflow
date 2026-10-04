# ADR-013: Tool System Audit (spec §22/§23)

**Status:** Accepted

## Context
Phase 9 built the tool execution engine. Phase 10 audits it against spec
§22's four required tool declarations (name, description, input schema,
output schema, permissions, risk level) and §23's security requirements,
rather than rebuilding — most of the engine was already correct.

## Finding 1 (real gap): no `output_schema` declared per tool
Spec §22 explicitly requires every tool to declare an output schema
alongside its input schema. Phase 9's `Tool` base class had `input_schema`
but nothing describing the shape of a successful result — `ToolResult.output`
was an untyped `dict[str, Any]`.

**Fix:** `Tool` now declares `output_schema: ClassVar[type[BaseModel]]`
alongside `input_schema`. `run()` validates a successful `_execute()`
result against `output_schema` before returning — catching a tool
implementation bug where actual output drifts from its documented shape,
not just documenting the shape and hoping implementations stay honest.
This is runtime validation, not a second generic type parameter: `_execute`
already returns the `ToolResult` dataclass rather than the raw output type,
so a second `TypeVar` would add type-system complexity without changing
what's statically checked — the value here is the actual validation call,
not the annotation.

## Finding 2 (real security gap, not theoretical): full `Settings` exposed to every tool, unused
`ToolExecutionContext` carried the complete `Settings` object — including
`jwt_secret`, every LLM provider's API key, and `database_url`/`redis_url`
(which embed credentials) — into every single tool call. Auditing actual
usage: **zero** of the six Phase 9 tools reference `context.settings` at
all. This is a latent violation of spec §23's "never expose secrets to the
model," not an active one — but it's a real attack surface, not a
hypothetical one: tool outputs are echoed into the LLM's conversation
transcript and persisted to `agent_steps.reasoning` (see
`agent_service._build_transcript`/`_summarize_output`), so a single
careless future tool implementation returning `context.settings.jwt_secret`
in its output would leak it directly into an LLM conversation and the
database — no additional bug required elsewhere.

**Fix:** `Settings` removed from `ToolExecutionContext` entirely. No tool
today needs any setting; if a future tool genuinely needs a specific
non-secret value (e.g. a size limit), it should receive that exact value as
its own field, not the whole settings object. This is least-privilege
applied at the type level — the *capability* to reach a secret is removed,
not just the current absence of code that does so.

## Finding 3 (real, but scoped as a deliberate non-fix): spec's named example tools not all present
Spec §22 lists `search_documents()`, `get_document()`, `search_database()`,
`run_safe_sql()`, `calculate()`, `generate_report()`, `create_ticket()`,
`draft_email()` as *example* tools. Six of eight exist (the two SQL-related
examples both map to `run_safe_sql`, which is the more concrete,
implementable version of "search_database"). Adding `draft_email` — a real,
safe, LOW/MEDIUM-risk tool that composes email *text* without sending
anything (no SMTP integration exists in this project) — closes one gap with
genuine substance. `create_ticket` is deliberately NOT added: there is no
ticketing domain anywhere in this application, and inventing one purely to
match an example tool's name would be exactly the kind of hollow,
substance-free feature the project's "no fake implementations" principle
rules out. If a real ticketing/support domain is added to the product later,
a `create_ticket` tool naturally follows from it — not the other way around.

## Finding 4 (real gap): no tool discovery/introspection API
Phase 9 built execution but nothing lets a caller (the eventual frontend, or
an admin) see what tools exist, their risk levels, and their schemas without
reading source code. **Fix:** `GET /api/v1/tools`, tenant-authenticated
(any role — this is metadata, not data), returning each tool's name,
description, risk level, allowed roles, and both schemas.

## Finding 5 (deferred from Phase 9, addressed now): agent evaluation metrics
Spec §27's second metric list (task success rate, tool selection accuracy,
unnecessary tool calls) was explicitly deferred in Phase 9 since no agent
existed yet to measure. `evaluation/agent_metrics.py` adds these as pure,
testable functions (same pattern as `retrieval_metrics.py`), plus a small
agent-specific golden dataset and a runner that exercises them against a
real `AgentService` run with injected fake providers — same honest
verification pattern as every LLM-dependent piece since ADR-008.

## Consequences
- `ToolResult` construction sites in all tools needed updating to match
  their declared `output_schema` — a real, if mechanical, change verified
  by tests asserting the validation actually rejects a mismatched shape,
  not just that it accepts a correct one.
- `ToolExecutionContext`'s reduced surface means any *future* tool that
  turns out to genuinely need a setting will get a deliberate, reviewed
  addition of that one field — friction that's the point, not a bug.

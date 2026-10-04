# ADR-012: Agent Planner Protocol, Execution Model, and Safe-SQL Design

**Status:** Accepted

## Context
ADR-005 already decided the state machine shape (Planning, ToolSelection,
ToolExecution, AwaitingApproval, Observation, Verification, Complete,
Failed, Rejected) and rejected LangGraph in favor of a custom
implementation. This ADR covers what ADR-005 left open: how the planner
actually talks to the LLM, how execution is scheduled (sync vs background),
and how the safe-SQL tool (spec §24) is genuinely made safe, not just
described as safe.

## Decision 1: ReAct-style JSON prompting, not native provider tool-calling
The planner asks the LLM to respond with a JSON object describing its next
action (`{"action": "tool_call", "tool": "...", "arguments": {...},
"reasoning": "..."}` or `{"action": "final_answer", "answer": "...",
"reasoning": "..."}`), parsed the same way Phase 8's LLM-judge parses
structured output — rather than extending `LLMProvider` (ADR-010) with
native function-calling.

**Reasoning:** Native tool-calling APIs differ meaningfully across
providers (Anthropic's block-based content format vs. Ollama's more limited,
model-dependent support), and `settings.llm_provider` defaults to Ollama
(ADR-004) for the target local-dev hardware. Building the agent on top of a
provider-specific tool-calling protocol would either weaken the Ollama path
or require two different code paths per provider. JSON-instructed output
works identically regardless of provider, needs zero changes to the
`LLMProvider` protocol from Phase 7, and is a well-established, legitimate
pattern (ReAct). The trade-off — slightly less reliable than native
structured output — is handled the same way Phase 8 handles judge-response
parsing failures: a distinct, catchable error type, never a silent
misparse.

## Decision 2: synchronous execution with a resumable approval endpoint, not a background job
An agent run executes synchronously within `POST /api/v1/agents` up to
`MAX_STEPS`/`MAX_RUNTIME_SECONDS`, pausing (not blocking) the moment it
selects a HIGH_RISK tool — the request returns immediately with the run in
`AWAITING_APPROVAL` state. A human decision at `POST
/api/v1/agents/{id}/approve` (or `/reject`) resumes the loop synchronously
from where it paused.

**Reasoning:** The alternative — running agent steps as arq background jobs,
resumable across process restarts — is a better production architecture but
substantially more complex (persisting/rehydrating LLM conversation state
across job boundaries, coordinating job re-enqueueing on approval). Given
`MAX_STEPS` is small (default 8) and each step is one bounded LLM call plus
a fast local tool execution, synchronous execution keeps latency reasonable
and the implementation correct and testable within this phase's scope.
**Known gap, tracked deliberately, not hidden:** long-running or many-step
agent workflows would benefit from background execution; this is a
reasonable future enhancement once there's evidence the synchronous model
is actually a bottleneck, not a redesign of the state machine itself.

## Decision 3: safe-SQL tool uses multiple independent, real safety layers
Per spec §24/§37, `run_safe_sql` must never allow a write, and must never
leak cross-tenant or sensitive (auth/credential) data. Rather than relying
on a single defense (e.g. keyword blocklisting, which has known bypass
techniques), the tool stacks four independent layers — each one closes a
different failure mode of the others:

1. **Statement shape validation**: must be a single `SELECT`, no semicolon-
   separated multi-statements, no comment-based obfuscation.
2. **Keyword blocklist**: rejects `INSERT/UPDATE/DELETE/DROP/ALTER/
   TRUNCATE/GRANT/REVOKE/CREATE/EXEC/CALL/COPY/pg_sleep` etc. via
   word-boundary matching (not naive substring matching, which would
   false-positive on legitimate column names).
3. **Table/view allowlist**: the query may only reference
   `agent_document_overview` — a dedicated, migration-defined view
   exposing only non-sensitive document metadata (id, filename, status,
   size, created_at, collection name, organization_id). It never joins to
   `users`, `refresh_tokens`, or any auth table, and never exposes
   `extracted_text` — so even a successful query cannot leak credentials,
   password hashes, or full document contents.
4. **Database-enforced read-only transaction**: the query executes inside
   an explicit Postgres read-only transaction (`SET TRANSACTION READ
   ONLY`). This is the layer that actually matters if the first three have
   a gap — the database itself refuses any write, regardless of what
   slipped through string-level validation.

Tenant scoping is enforced by wrapping the validated query as a subquery
with an outer, tool-authored (never LLM-authored) `WHERE organization_id =
:org_id` — the LLM's query must project `organization_id` (enforced by
validation) but never controls the tenant filter itself.

## Decision 4: tool permissions are gated by the initiating user's role, not the agent's
An agent run is started by an authenticated user with a real membership
role. Every tool declares a minimum required role; the agent may only
select and execute tools the initiating user's own role would already be
allowed to use directly (e.g. `delete_document` requires ADMIN/MANAGER,
matching the existing document-delete permission from Phase 4). The agent
is never granted authority the human who started it doesn't already have —
per spec §21/§37, the agent must not be able to bypass system security
policies just because it's acting autonomously.

## Consequences
- No changes needed to `LLMProvider`/`AnthropicProvider`/`OllamaProvider`
  from Phase 7 — the planner is a pure consumer of the existing `complete()`
  method.
- The planner's JSON parsing is unit-testable with a `FakeLLMProvider`
  exactly like Phase 8's judge parsing, without needing a real model.
- `run_safe_sql`'s four layers are independently unit-testable — including
  proving layer 4 (the DB-level read-only transaction) actually stops a
  write that a hypothetical gap in layers 1-3 let through, using real
  Postgres, not a mock.

# ADR-016: Agent Run UI and Human-Approval Gating

**Status:** Accepted

## Context
Phase 12 explicitly deferred agent UI (ADR-015 decision 6) as its own
focused phase. This ADR covers the UI-specific decisions for surfacing a
real agent run, including a genuine human-approval gate for HIGH_RISK tool
calls — not a decorative confirm dialog, but a real block on execution the
backend already enforces (ADR-005/012).

## Decision 1: the loading state during start/approve/reject must say what's actually happening
`POST /api/v1/agents`, `.../approve`, and `.../reject` are all synchronous
backend calls (ADR-012 decision 2) that can legitimately take up to
`MAX_RUNTIME_SECONDS` (90s default) before returning — the run executes to
completion, failure, or the next approval pause *within that single
request*. A bare spinner for up to 90 seconds reads as broken. The loading
state names what's actually happening ("The agent is working — this can
take up to a minute") rather than implying something is stuck.

## Decision 2: steps and tool calls are shown as two honest, separate sections, not a fabricated timeline
`AgentStepResponse` has no `tool_call_id`, and `ToolCallResponse` has no
timestamp — the API genuinely does not expose a way to correlate a specific
reasoning step to a specific tool call, or to interleave them
chronologically with each other. Rather than guess at an interleaved
timeline the data doesn't support (which would misrepresent the real
sequence some of the time), the UI shows two separate sections: an ordered
reasoning timeline (`steps`, by `step_index`) and a tool-calls list
(`tool_calls`, each with its own risk level, status, input/output, and
approval state). This is a real, stated limitation of the current API
response shape — a natural follow-up would add the correlation fields
backend-side so the UI can do better, tracked in PLAN.md rather than faked
here.

## Decision 3: the approval panel is visually unmistakable, not a routine confirm dialog
Per spec §25, approval must be a real gate, not UI decoration — the backend
already enforces this (a HIGH_RISK tool never executes without a stored
`Approval` row transitioning to `approved`). The UI reinforces this rather
than undermining it with a throwaway-feeling confirm: when a run is
`awaiting_approval`, the pending tool call renders in a dedicated panel
using the brick/danger color, showing the tool name, its declared risk
level, and its full input arguments (not a summary) before either action is
available. Reject is the visually calmer default (secondary-style button);
Approve uses the danger-style button — deliberately inverting the usual
"primary action is the emphasized one" convention, because for an
irreversible high-risk action, calm should be the default posture and
approval should require the more deliberate reach.

## Decision 4: `input_data`/`output_data` render generically, not per-tool-typed
These fields are `dict[str, Any]` on the backend (necessarily — six
different tools have six different argument/result shapes) and generated
as `Record<string, never>` by openapi-typescript, since there's no more
specific OpenAPI shape to generate from a genuinely dynamic dict. Rendered
as a simple key/value list via `Object.entries()`, not a per-tool-specific
form — building six bespoke renderers for six tools is more code than the
value justifies at this stage, and a generic renderer degrades gracefully
if a seventh tool is added later without frontend changes.

## Consequences
- No polling is needed for run status the way document processing needs it
  (Phase 12) — the synchronous call model means the response already
  reflects the run's current terminal/paused state.
- `/agents/[runId]` is the single source of truth after any action
  (start/approve/reject) — each mutation's response updates the same
  detail view rather than triggering a separate re-fetch.

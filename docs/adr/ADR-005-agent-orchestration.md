# ADR-005: Agent Orchestration

**Status:** Accepted

## Context
Need a controlled agent (planner → tool selection → execution → verification) with
hard step/runtime/tool-call limits and mandatory human approval for high-risk actions.
Spec allows LangGraph "if it provides genuine value," otherwise a clean internal layer.

## Decision
A custom, explicit state machine (see `docs/architecture/overview.md` §4) implemented
directly in the application, with every state transition persisted to
`agent_runs`/`agent_steps`/`tool_calls`/`approvals`.

## Alternatives considered
**LangGraph** — genuinely good at expressing graph-based agent flows, but for this
spec's requirements (deterministic transitions, hard-coded MAX_STEPS/MAX_RUNTIME,
mandatory synchronous approval gate before high-risk execution, full state
inspectability for the admin dashboard and audit log) a custom state machine gives:
- no framework-imposed abstractions to work around for the approval gate
- state persisted directly in schema this project already owns (queryable by the
  admin dashboard/evaluation harness without translating a framework's internal state)
- fewer dependencies to pin/patch/audit for security

## Reasoning
The workflow here is a small, fixed set of states (Planning, ToolSelection,
ToolExecution, AwaitingApproval, Observation, Verification, Complete, Failed,
Rejected) — not an open-ended graph that benefits from a general graph-orchestration
framework. A ~200-line explicit state machine is easier to security-review, test
exhaustively (including the injection-resistance tests in section 38), and reason
about than a framework dependency doing the same job less transparently.

## Trade-offs
- Forgoes LangGraph's ecosystem (pre-built nodes, visualizers) — acceptable since the
  admin dashboard (section 32) already needs to render agent state directly from our
  own schema regardless of orchestration engine.
- More code to own directly rather than delegating to a maintained framework.

## Consequences
- Full control over where the approval gate is enforced (server-side, not bypassable).
- If a future need for more complex branching agent workflows arises, this decision
  should be revisited with actual evidence, not assumed up front.

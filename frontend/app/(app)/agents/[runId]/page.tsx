"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { RiskBadge, StatusBadge } from "@/components/agent-badges";
import { KeyValueList } from "@/components/key-value-list";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/client";
import { useAgentRun, useDecideApproval } from "@/lib/api/hooks";
import { useOrg } from "@/lib/auth/org-context";

type AgentStepState = Schemas["AgentStepState"];

const STEP_LABELS: Record<AgentStepState, string> = {
  planning: "Planning",
  tool_selection: "Selecting a tool",
  tool_execution: "Executing",
  observation: "Observation",
  verification: "Verifying",
};

export default function AgentRunPage() {
  const { currentOrgId } = useOrg();
  const params = useParams<{ runId: string }>();
  const runQuery = useAgentRun(currentOrgId, params.runId);
  const decideApproval = useDecideApproval(currentOrgId, params.runId);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decidingApprovalId, setDecidingApprovalId] = useState<string | null>(null);

  if (runQuery.isLoading) {
    return <p className="p-10 text-sm text-ink-500">Loading…</p>;
  }
  const run = runQuery.data;
  if (!run) {
    return <p className="p-10 text-sm text-ink-500">Run not found.</p>;
  }

  const pendingToolCall = run.tool_calls.find(
    (tc) => tc.status === "awaiting_approval" && tc.approval?.status === "pending",
  );

  async function handleDecision(approvalId: string, approved: boolean) {
    setDecisionError(null);
    setDecidingApprovalId(approvalId);
    try {
      await decideApproval.mutateAsync({ approvalId, approved });
    } catch (err) {
      setDecisionError(
        err instanceof ApiError ? err.message : "Could not record your decision. Try again.",
      );
    } finally {
      setDecidingApprovalId(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-8 py-10">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-xl font-semibold text-ink-900">{run.goal}</h1>
          <p className="mt-1 font-mono text-xs text-ink-300">
            {run.step_count} / {run.max_steps} steps
          </p>
        </div>
        <StatusBadge status={run.status} />
      </div>

      {run.final_answer && (
        <div className="mb-8 rounded-lg border border-forest-dim bg-forest-dim/40 p-4">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-forest">
            Final answer
          </p>
          <p className="whitespace-pre-wrap text-sm text-ink-900">{run.final_answer}</p>
        </div>
      )}

      {run.error_message && (
        <div className="mb-8 rounded-lg border border-brick-dim bg-brick-dim/40 p-4">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-brick">Error</p>
          <p className="text-sm text-ink-900">{run.error_message}</p>
        </div>
      )}

      {pendingToolCall && pendingToolCall.approval && (
        <div className="mb-8 rounded-lg border-2 border-brick bg-brick-dim/30 p-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-brick">
            Approval needed before this action runs
          </p>
          <div className="mb-3 flex items-center gap-2">
            <span className="font-mono text-sm font-medium text-ink-900">
              {pendingToolCall.tool_name}
            </span>
            <RiskBadge risk={pendingToolCall.risk_level} />
          </div>
          <div className="mb-4 rounded border border-ink-100 bg-white p-3">
            <KeyValueList data={pendingToolCall.input_data} />
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="danger"
              disabled={decidingApprovalId !== null}
              onClick={() => handleDecision(pendingToolCall.approval!.id, true)}
            >
              {decidingApprovalId === pendingToolCall.approval.id ? "Working…" : "Approve and run"}
            </Button>
            <Button
              variant="secondary"
              disabled={decidingApprovalId !== null}
              onClick={() => handleDecision(pendingToolCall.approval!.id, false)}
            >
              Reject
            </Button>
          </div>
          {decisionError && <p className="mt-3 text-sm text-brick">{decisionError}</p>}
        </div>
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-ink-700">Reasoning</h2>
        <ol className="flex flex-col gap-3">
          {run.steps.map((step) => (
            <li key={step.step_index} className="rounded border border-ink-100 bg-white px-3 py-2.5">
              <p className="mb-1 font-mono text-xs text-ink-300">{STEP_LABELS[step.state]}</p>
              <p className="whitespace-pre-wrap text-sm text-ink-900">{step.reasoning}</p>
            </li>
          ))}
          {run.steps.length === 0 && (
            <p className="text-sm text-ink-300">No steps recorded yet.</p>
          )}
        </ol>
      </section>

      {run.tool_calls.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-ink-700">Tool calls</h2>
          <ul className="flex flex-col gap-3">
            {run.tool_calls.map((toolCall) => (
              <li key={toolCall.id} className="rounded border border-ink-100 bg-white p-3">
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-mono text-sm font-medium text-ink-900">
                    {toolCall.tool_name}
                  </span>
                  <RiskBadge risk={toolCall.risk_level} />
                  <span className="ml-auto font-mono text-xs text-ink-300">
                    {toolCall.status}
                  </span>
                </div>
                <p className="mb-1 text-xs font-medium text-ink-500">Input</p>
                <KeyValueList data={toolCall.input_data} />
                {toolCall.output_data && (
                  <>
                    <p className="mb-1 mt-2 text-xs font-medium text-ink-500">Output</p>
                    <KeyValueList data={toolCall.output_data} />
                  </>
                )}
                {toolCall.error_message && (
                  <p className="mt-2 text-xs text-brick">{toolCall.error_message}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

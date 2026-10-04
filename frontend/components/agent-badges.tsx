import type { Schemas } from "@/lib/api/client";

type ToolRiskLevel = Schemas["ToolRiskLevel"];
type AgentRunStatus = Schemas["AgentRunStatus"];

// Deliberately not reusing the amber accent here (ADR-015 reserves it for
// citations only) — risk levels get their own distinct treatment so amber
// keeps meaning one specific thing everywhere it appears.
const RISK_STYLES: Record<ToolRiskLevel, string> = {
  low: "bg-ink-50 text-ink-500",
  medium: "border border-ink-300 text-ink-700",
  high: "bg-brick-dim text-brick",
};

export function RiskBadge({ risk }: { risk: ToolRiskLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded-sm px-2 py-0.5 font-mono text-xs font-medium uppercase tracking-wide ${RISK_STYLES[risk]}`}
    >
      {risk}
    </span>
  );
}

const STATUS_STYLES: Record<AgentRunStatus, string> = {
  running: "bg-ink-50 text-ink-500",
  awaiting_approval: "bg-brick-dim text-brick",
  completed: "bg-forest-dim text-forest",
  failed: "bg-brick-dim text-brick",
  rejected: "border border-ink-300 text-ink-500",
};

const STATUS_LABELS: Record<AgentRunStatus, string> = {
  running: "Running",
  awaiting_approval: "Needs approval",
  completed: "Completed",
  failed: "Failed",
  rejected: "Rejected",
};

export function StatusBadge({ status }: { status: AgentRunStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-sm px-2 py-1 font-mono text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

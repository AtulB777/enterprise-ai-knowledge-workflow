"use client";

import Link from "next/link";
import { useEvaluationRuns } from "@/lib/api/hooks";

const STATUS_STYLES: Record<string, string> = {
  running: "bg-ink-50 text-ink-500",
  completed: "bg-forest-dim text-forest",
  failed: "bg-brick-dim text-brick",
};

function formatMetric(value: unknown): string {
  if (typeof value === "number") return value.toFixed(2);
  return String(value);
}

export default function EvaluationRunsPage() {
  const { data, isLoading } = useEvaluationRuns();
  const runs = data?.items ?? [];

  return (
    <div className="mx-auto w-full max-w-4xl px-8 py-10">
      <h1 className="mb-1 font-display text-2xl font-semibold text-ink-900">Evaluation runs</h1>
      <p className="mb-8 text-sm text-ink-500">
        Every run of <code className="font-mono text-xs">python -m evaluation.run</code>, across
        all datasets — not scoped to any one organization.
      </p>

      {isLoading && <p className="text-sm text-ink-500">Loading…</p>}

      {data && runs.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink-100 px-6 py-16 text-center">
          <p className="text-sm text-ink-500">No evaluation runs yet.</p>
        </div>
      )}

      {runs.length > 0 && (
        <ul className="flex flex-col divide-y divide-ink-100 rounded-lg border border-ink-100 bg-white">
          {runs.map((run) => (
            <li key={run.id}>
              <Link
                href={`/admin/evaluations/${run.id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-ink-50"
              >
                <div className="min-w-0">
                  <p className="font-mono text-sm text-ink-900">{run.dataset_version}</p>
                  <p className="mt-0.5 font-mono text-xs text-ink-300">
                    {new Date(run.started_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {Object.entries(run.summary_metrics)
                    .slice(0, 3)
                    .map(([key, value]) => (
                      <span key={key} className="font-mono text-xs text-ink-500">
                        {key}: {formatMetric(value)}
                      </span>
                    ))}
                  <span
                    className={`rounded-sm px-2 py-1 font-mono text-xs font-medium ${STATUS_STYLES[run.status] ?? ""}`}
                  >
                    {run.status}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

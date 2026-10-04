"use client";

import { useParams } from "next/navigation";
import { useEvaluationRun } from "@/lib/api/hooks";

function formatMetric(value: unknown): string {
  if (typeof value === "number") return value.toFixed(3);
  return String(value);
}

export default function EvaluationRunDetailPage() {
  const params = useParams<{ runId: string }>();
  const { data: run, isLoading } = useEvaluationRun(params.runId);

  if (isLoading) {
    return <p className="p-10 text-sm text-ink-500">Loading…</p>;
  }
  if (!run) {
    return <p className="p-10 text-sm text-ink-500">Run not found.</p>;
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-8 py-10">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-semibold text-ink-900">
            {run.dataset_version}
          </h1>
          <p className="mt-1 font-mono text-xs text-ink-300">
            {new Date(run.started_at).toLocaleString()}
          </p>
        </div>
        <span className="rounded-sm bg-ink-50 px-2 py-1 font-mono text-xs font-medium text-ink-700">
          {run.status}
        </span>
      </div>

      {run.error_message && (
        <div className="mb-8 rounded-lg border border-brick-dim bg-brick-dim/40 p-4">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-brick">Error</p>
          <p className="text-sm text-ink-900">{run.error_message}</p>
        </div>
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-ink-700">Summary metrics</h2>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {Object.entries(run.summary_metrics).map(([key, value]) => (
            <div key={key} className="rounded border border-ink-100 bg-white p-3">
              <dt className="font-mono text-xs text-ink-300">{key}</dt>
              <dd className="mt-0.5 font-mono text-sm text-ink-900">{formatMetric(value)}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-ink-700">
          Per-case results ({run.results.length})
        </h2>
        <ul className="flex flex-col gap-3">
          {run.results.map((result) => (
            <li key={result.id} className="rounded border border-ink-100 bg-white p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="font-mono text-sm font-medium text-ink-900">
                  {result.case_id}
                </span>
                {result.latency_ms !== null && (
                  <span className="font-mono text-xs text-ink-300">
                    {result.latency_ms.toFixed(0)} ms
                  </span>
                )}
              </div>
              <p className="mb-2 text-sm text-ink-700">{result.query}</p>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {Object.entries(result.metrics).map(([key, value]) => (
                  <span key={key} className="font-mono text-xs text-ink-500">
                    {key}: {formatMetric(value)}
                  </span>
                ))}
              </div>
              {result.error_message && (
                <p className="mt-2 text-xs text-brick">{result.error_message}</p>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

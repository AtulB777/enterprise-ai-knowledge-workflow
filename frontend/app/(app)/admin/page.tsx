"use client";

import Link from "next/link";
import { MetricCard } from "@/components/metric-card";
import { useMetricsSummary } from "@/lib/api/hooks";

function formatMs(value: number | null): string {
  if (value === null) return "—";
  return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function AdminDashboardPage() {
  const { data, isLoading } = useMetricsSummary();

  return (
    <div className="mx-auto w-full max-w-4xl px-8 py-10">
      <div className="mb-2 flex items-baseline justify-between">
        <h1 className="font-display text-2xl font-semibold text-ink-900">Admin</h1>
        <Link
          href="/admin/evaluations"
          className="text-sm text-ink-500 underline hover:text-ink-900"
        >
          Evaluation runs →
        </Link>
      </div>
      <p className="mb-8 text-sm text-ink-500">
        A live snapshot of activity since this server process started — not a historical
        chart. Refreshes automatically every 10 seconds.
      </p>

      {isLoading && <p className="text-sm text-ink-500">Loading…</p>}

      {data && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <MetricCard label="Total requests" value={data.total_requests.toLocaleString()} />
          <MetricCard
            label="Errors"
            value={data.total_errors.toLocaleString()}
            emphasis={data.total_errors > 0 ? "danger" : "default"}
          />
          <MetricCard label="Error rate" value={formatPercent(data.error_rate)} />
          <MetricCard label="Avg request latency" value={formatMs(data.avg_request_latency_ms)} />
          <MetricCard
            label="Avg retrieval latency"
            value={formatMs(data.avg_retrieval_latency_ms)}
          />
          <MetricCard label="Avg LLM latency" value={formatMs(data.avg_llm_latency_ms)} />
          <MetricCard
            label="Tokens (in / out)"
            value={`${data.total_input_tokens.toLocaleString()} / ${data.total_output_tokens.toLocaleString()}`}
          />
          <MetricCard
            label="Estimated LLM cost"
            value={`$${data.total_estimated_cost_usd.toFixed(4)}`}
          />
          <MetricCard label="Agent steps" value={data.total_agent_steps.toLocaleString()} />
          <MetricCard
            label="Rate limit rejections"
            value={data.total_rate_limit_rejections.toLocaleString()}
            emphasis={data.total_rate_limit_rejections > 0 ? "danger" : "default"}
          />
        </div>
      )}
    </div>
  );
}

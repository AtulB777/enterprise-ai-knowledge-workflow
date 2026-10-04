"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { StatusBadge } from "@/components/agent-badges";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useAgentRuns, useStartAgentRun } from "@/lib/api/hooks";
import { useOrg } from "@/lib/auth/org-context";

const WORKING_MESSAGES = [
  "The agent is working — this can take up to a minute.",
  "Still going — reasoning through the next step…",
  "Almost there — wrapping up or checking whether it needs your approval…",
];

function useElapsedSeconds(active: boolean) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [active]);
  return [seconds, () => setSeconds(0)] as const;
}

export default function AgentsPage() {
  const { currentOrgId } = useOrg();
  const runsQuery = useAgentRuns(currentOrgId);
  const startRun = useStartAgentRun(currentOrgId);
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [elapsed, resetElapsed] = useElapsedSeconds(startRun.isPending);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed) return;
    setError(null);
    resetElapsed();
    try {
      const run = await startRun.mutateAsync(trimmed);
      setGoal("");
      router.push(`/agents/${run.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the agent. Try again.");
    }
  }

  const runs = runsQuery.data?.items ?? [];
  const workingMessage =
    WORKING_MESSAGES[Math.min(Math.floor(elapsed / 15), WORKING_MESSAGES.length - 1)];

  return (
    <div className="mx-auto w-full max-w-3xl px-8 py-10">
      <h1 className="mb-1 font-display text-2xl font-semibold text-ink-900">Agents</h1>
      <p className="mb-8 text-sm text-ink-500">
        Give the agent a goal. It can search documents, run calculations, and — with your
        approval — take actions like deleting a document.
      </p>

      <form
        onSubmit={handleSubmit}
        className="mb-10 flex flex-col gap-3 rounded-lg border border-ink-100 bg-white p-4"
      >
        <label htmlFor="agent-goal" className="text-sm font-medium text-ink-700">
          What should the agent do?
        </label>
        <textarea
          id="agent-goal"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          rows={2}
          placeholder="e.g. Summarize what our documents say about the remote work policy."
          disabled={startRun.isPending}
          className="resize-none rounded border border-ink-300 bg-white px-3 py-2 text-sm text-ink-900 placeholder:text-ink-300 focus:border-ink-900 focus:outline-none focus:ring-1 focus:ring-ink-900"
        />
        <div className="flex items-center justify-between gap-4">
          {startRun.isPending ? (
            <p className="font-mono text-xs text-ink-500">
              {workingMessage} ({elapsed}s)
            </p>
          ) : (
            <span />
          )}
          <Button
            type="submit"
            disabled={startRun.isPending || !goal.trim() || currentOrgId === null}
          >
            {startRun.isPending ? "Working…" : "Start"}
          </Button>
        </div>
        {error && (
          <p role="alert" className="rounded bg-brick-dim px-3 py-2 text-sm text-brick">
            {error}
          </p>
        )}
      </form>

      {runsQuery.isLoading && <p className="text-sm text-ink-500">Loading runs…</p>}

      {runsQuery.isSuccess && runs.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink-100 px-6 py-16 text-center">
          <p className="text-sm text-ink-500">No agent runs yet.</p>
        </div>
      )}

      {runs.length > 0 && (
        <ul className="flex flex-col divide-y divide-ink-100 rounded-lg border border-ink-100 bg-white">
          {runs.map((run) => (
            <li key={run.id}>
              <Link
                href={`/agents/${run.id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-ink-50"
              >
                <p className="min-w-0 truncate text-sm text-ink-900">{run.goal}</p>
                <StatusBadge status={run.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

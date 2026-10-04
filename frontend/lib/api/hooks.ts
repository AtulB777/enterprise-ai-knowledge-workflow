import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/client";

type DocumentResponse = Schemas["DocumentResponse"];
type DocumentListResponse = Schemas["DocumentListResponse"];
type ConversationResponse = Schemas["ConversationResponse"];
type ConversationListResponse = Schemas["ConversationListResponse"];
type ConversationDetailResponse = Schemas["ConversationDetailResponse"];
type MessageResponse = Schemas["MessageResponse"];
type AgentRunDetailResponse = Schemas["AgentRunDetailResponse"];
type AgentRunListResponse = Schemas["AgentRunListResponse"];
type ToolInfoResponse = Schemas["ToolInfoResponse"];
type MetricsSummaryResponse = Schemas["MetricsSummaryResponse"];
type EvaluationRunListResponse = Schemas["EvaluationRunListResponse"];
type EvaluationRunDetailResponse = Schemas["EvaluationRunDetailResponse"];

// --- Documents ---

export function useDocuments(orgId: string | null) {
  return useQuery({
    queryKey: ["documents", orgId],
    queryFn: () =>
      apiFetch<DocumentListResponse>("/api/v1/documents", {
        query: { organization_id: orgId ?? undefined },
      }),
    enabled: orgId !== null,
    // Documents transition pending -> processing -> completed/failed in the
    // background (arq worker) — poll while any are still in flight so the
    // list reflects real status changes without a manual refresh.
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const hasInFlight = items.some((d) => d.status === "pending" || d.status === "processing");
      return hasInFlight ? 2000 : false;
    },
  });
}

export function useUploadDocument(orgId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiFetch<DocumentResponse>("/api/v1/documents", {
        method: "POST",
        query: { organization_id: orgId ?? undefined },
        body: formData,
        isFormData: true,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", orgId] });
    },
  });
}

export function useDeleteDocument(orgId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (documentId: string) => {
      return apiFetch<void>(`/api/v1/documents/${documentId}`, {
        method: "DELETE",
        query: { organization_id: orgId ?? undefined },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", orgId] });
    },
  });
}

// --- Conversations ---

export function useConversations(orgId: string | null) {
  return useQuery({
    queryKey: ["conversations", orgId],
    queryFn: () =>
      apiFetch<ConversationListResponse>("/api/v1/conversations", {
        query: { organization_id: orgId ?? undefined },
      }),
    enabled: orgId !== null,
  });
}

export function useConversation(orgId: string | null, conversationId: string | null) {
  return useQuery({
    queryKey: ["conversation", orgId, conversationId],
    queryFn: () =>
      apiFetch<ConversationDetailResponse>(`/api/v1/conversations/${conversationId}`, {
        query: { organization_id: orgId ?? undefined },
      }),
    enabled: orgId !== null && conversationId !== null,
  });
}

export function useCreateConversation(orgId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      apiFetch<ConversationResponse>("/api/v1/conversations", {
        method: "POST",
        query: { organization_id: orgId ?? undefined },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations", orgId] });
    },
  });
}

export function useAskQuestion(orgId: string | null, conversationId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (question: string) =>
      apiFetch<MessageResponse>(`/api/v1/conversations/${conversationId}/messages`, {
        method: "POST",
        query: { organization_id: orgId ?? undefined },
        body: { question },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversation", orgId, conversationId] });
      queryClient.invalidateQueries({ queryKey: ["conversations", orgId] });
    },
  });
}

// --- Agents ---

export function useAgentRuns(orgId: string | null) {
  return useQuery({
    queryKey: ["agent-runs", orgId],
    queryFn: () =>
      apiFetch<AgentRunListResponse>("/api/v1/agents", {
        query: { organization_id: orgId ?? undefined },
      }),
    enabled: orgId !== null,
  });
}

export function useAgentRun(orgId: string | null, runId: string | null) {
  return useQuery({
    queryKey: ["agent-run", orgId, runId],
    queryFn: () =>
      apiFetch<AgentRunDetailResponse>(`/api/v1/agents/${runId}`, {
        query: { organization_id: orgId ?? undefined },
      }),
    enabled: orgId !== null && runId !== null,
  });
}

export function useStartAgentRun(orgId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    // Synchronous on the backend (ADR-012 decision 2, ADR-016 decision 1):
    // this resolves only once the run reaches completed/failed/
    // awaiting_approval, up to MAX_RUNTIME_SECONDS — not a fire-and-forget
    // job kickoff. Returns AgentRunDetailResponse (confirmed against the
    // real route's response_model), not the summary-only AgentRunResponse.
    mutationFn: async (goal: string) =>
      apiFetch<AgentRunDetailResponse>("/api/v1/agents", {
        method: "POST",
        query: { organization_id: orgId ?? undefined },
        body: { goal },
      }),
    onSuccess: (run) => {
      queryClient.setQueryData(["agent-run", orgId, run.id], run);
      queryClient.invalidateQueries({ queryKey: ["agent-runs", orgId] });
    },
  });
}

export function useDecideApproval(orgId: string | null, runId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      approvalId,
      approved,
      notes,
    }: {
      approvalId: string;
      approved: boolean;
      notes?: string;
    }) =>
      apiFetch<AgentRunDetailResponse>(
        `/api/v1/agents/approvals/${approvalId}/${approved ? "approve" : "reject"}`,
        {
          method: "POST",
          query: { organization_id: orgId ?? undefined },
          body: { notes: notes ?? null },
        },
      ),
    onSuccess: (updatedRun) => {
      queryClient.setQueryData(["agent-run", orgId, runId], updatedRun);
      queryClient.invalidateQueries({ queryKey: ["agent-runs", orgId] });
    },
  });
}

export function useTools() {
  return useQuery({
    queryKey: ["tools"],
    queryFn: () => apiFetch<ToolInfoResponse[]>("/api/v1/tools"),
    staleTime: 5 * 60_000,
  });
}

// --- Admin dashboard ---

export function useMetricsSummary() {
  return useQuery({
    queryKey: ["admin-metrics-summary"],
    queryFn: () => apiFetch<MetricsSummaryResponse>("/api/v1/admin/metrics-summary"),
    // A live snapshot (ADR-018 decision 3), not a historical series — safe
    // and useful to refresh periodically rather than caching for long.
    refetchInterval: 10_000,
  });
}

export function useEvaluationRuns() {
  return useQuery({
    queryKey: ["admin-evaluation-runs"],
    queryFn: () => apiFetch<EvaluationRunListResponse>("/api/v1/admin/evaluations"),
  });
}

export function useEvaluationRun(runId: string | null) {
  return useQuery({
    queryKey: ["admin-evaluation-run", runId],
    queryFn: () =>
      apiFetch<EvaluationRunDetailResponse>(`/api/v1/admin/evaluations/${runId}`),
    enabled: runId !== null,
  });
}

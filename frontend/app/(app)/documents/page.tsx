"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/client";
import { useDeleteDocument, useDocuments, useUploadDocument } from "@/lib/api/hooks";
import { useOrg } from "@/lib/auth/org-context";

type DocumentResponse = Schemas["DocumentResponse"];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const STATUS_STYLES: Record<DocumentResponse["status"], string> = {
  pending: "bg-ink-50 text-ink-500",
  processing: "bg-amber-dim text-amber-deep",
  completed: "bg-forest-dim text-forest",
  failed: "bg-brick-dim text-brick",
};

export default function DocumentsPage() {
  const { currentOrgId } = useOrg();
  const documentsQuery = useDocuments(currentOrgId);
  const uploadMutation = useUploadDocument(currentOrgId);
  const deleteMutation = useDeleteDocument(currentOrgId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    try {
      await uploadMutation.mutateAsync(file);
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const documents = documentsQuery.data?.items ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl px-8 py-10">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-ink-900">Documents</h1>
          <p className="mt-1 text-sm text-ink-500">
            Upload documents to make them searchable and citable in chat.
          </p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileChange}
            accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.pptx"
          />
          <Button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending || currentOrgId === null}
          >
            {uploadMutation.isPending ? "Uploading…" : "Upload document"}
          </Button>
        </div>
      </div>

      {uploadError && (
        <p role="alert" className="mb-6 rounded bg-brick-dim px-3 py-2 text-sm text-brick">
          {uploadError}
        </p>
      )}

      {documentsQuery.isLoading && <p className="text-sm text-ink-500">Loading documents…</p>}

      {documentsQuery.isSuccess && documents.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink-100 px-6 py-16 text-center">
          <p className="text-sm text-ink-500">
            No documents yet. Upload one to start building your knowledge base.
          </p>
        </div>
      )}

      {documents.length > 0 && (
        <ul className="flex flex-col divide-y divide-ink-100 rounded-lg border border-ink-100 bg-white">
          {documents.map((doc) => (
            <li key={doc.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink-900">
                  {doc.original_filename}
                </p>
                <p className="mt-0.5 font-mono text-xs text-ink-300">
                  {formatBytes(doc.size_bytes)}
                  {doc.status === "failed" && doc.processing_error
                    ? ` · ${doc.processing_error}`
                    : ""}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span
                  className={`rounded-sm px-2 py-1 font-mono text-xs font-medium ${STATUS_STYLES[doc.status]}`}
                >
                  {doc.status}
                </span>
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(doc.id)}
                  disabled={deleteMutation.isPending}
                  className="text-sm text-ink-300 hover:text-brick"
                  aria-label={`Delete ${doc.original_filename}`}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

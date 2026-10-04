"use client";

import { useState } from "react";
import type { Schemas } from "@/lib/api/client";

type CitationResponse = Schemas["CitationResponse"];

export function CitationChip({ citation }: { citation: CitationResponse }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-amber bg-amber-dim px-1 font-mono text-xs font-medium text-amber-deep hover:bg-amber hover:text-white"
      >
        {citation.citation_number}
      </button>
      {isOpen && (
        <span className="absolute left-0 top-full z-10 mt-2 block w-80 rounded-lg border border-ink-100 bg-white p-4 shadow-lg">
          <span className="mb-2 flex items-center justify-between gap-2">
            <span className="truncate font-mono text-xs text-ink-500">
              {citation.document_filename}
            </span>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Close citation"
              className="text-ink-300 hover:text-ink-900"
            >
              ×
            </button>
          </span>
          <span className="block border-l-2 border-amber bg-amber-dim/40 py-1 pl-3 text-sm leading-relaxed text-ink-700">
            {citation.chunk_content}
          </span>
        </span>
      )}
    </span>
  );
}

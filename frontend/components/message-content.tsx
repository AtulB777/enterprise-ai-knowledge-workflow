import { Fragment } from "react";
import { CitationChip } from "@/components/citation-chip";
import type { Schemas } from "@/lib/api/client";

type CitationResponse = Schemas["CitationResponse"];

const CITATION_MARKER = /\[(\d+)]/g;

export function MessageContent({
  content,
  citations,
}: {
  content: string;
  citations: CitationResponse[];
}) {
  const citationsByNumber = new Map(citations.map((c) => [c.citation_number, c]));
  const parts: (string | { number: number })[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(CITATION_MARKER)) {
    const number = Number(match[1]);
    // Only treat [N] as a citation marker if it's a real, validated
    // citation this answer actually has — otherwise leave the literal
    // text alone rather than rendering a broken/empty chip.
    if (!citationsByNumber.has(number)) continue;
    const matchIndex = match.index ?? 0;
    if (matchIndex > lastIndex) {
      parts.push(content.slice(lastIndex, matchIndex));
    }
    parts.push({ number });
    lastIndex = matchIndex + match[0].length;
  }
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }

  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-900">
      {parts.map((part, index) =>
        typeof part === "string" ? (
          <Fragment key={index}>{part}</Fragment>
        ) : (
          <CitationChip key={index} citation={citationsByNumber.get(part.number)!} />
        ),
      )}
    </p>
  );
}

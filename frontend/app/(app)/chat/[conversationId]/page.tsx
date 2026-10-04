"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { MessageContent } from "@/components/message-content";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useAskQuestion, useConversation } from "@/lib/api/hooks";
import { useOrg } from "@/lib/auth/org-context";

export default function ConversationPage() {
  const { currentOrgId } = useOrg();
  const params = useParams<{ conversationId: string }>();
  const conversationId = params.conversationId;
  const conversationQuery = useConversation(currentOrgId, conversationId);
  const askQuestion = useAskQuestion(currentOrgId, conversationId);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  const messages = conversationQuery.data?.messages ?? [];

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    setError(null);
    setQuestion("");
    try {
      await askQuestion.mutateAsync(trimmed);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not get an answer. Try again.");
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex-1 overflow-y-auto px-8 py-8">
        <div className="mx-auto flex max-w-2xl flex-col gap-6">
          {conversationQuery.isLoading && <p className="text-sm text-ink-500">Loading…</p>}
          {messages.map((message) => (
            <div
              key={message.id}
              className={message.role === "user" ? "self-end text-right" : "self-start"}
            >
              <div
                className={`inline-block max-w-lg rounded-lg px-4 py-3 text-left ${
                  message.role === "user"
                    ? "bg-ink-900 text-paper"
                    : "border border-ink-100 bg-white"
                }`}
              >
                {message.role === "user" ? (
                  <p className="whitespace-pre-wrap text-sm">{message.content}</p>
                ) : (
                  <MessageContent content={message.content} citations={message.citations} />
                )}
              </div>
            </div>
          ))}
          {askQuestion.isPending && (
            <div className="self-start rounded-lg border border-ink-100 bg-white px-4 py-3 text-sm text-ink-300">
              Thinking…
            </div>
          )}
          <div ref={scrollAnchorRef} />
        </div>
      </div>

      <div className="border-t border-ink-100 bg-white px-8 py-4">
        <form onSubmit={handleSubmit} className="mx-auto flex max-w-2xl items-end gap-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder="Ask a question about your documents…"
            rows={1}
            className="flex-1 resize-none rounded border border-ink-300 bg-white px-3 py-2 text-sm text-ink-900 placeholder:text-ink-300 focus:border-ink-900 focus:outline-none focus:ring-1 focus:ring-ink-900"
          />
          <Button type="submit" disabled={askQuestion.isPending || !question.trim()}>
            Ask
          </Button>
        </form>
        {error && (
          <p role="alert" className="mx-auto mt-2 max-w-2xl text-sm text-brick">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

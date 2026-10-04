"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useCreateConversation, useConversations } from "@/lib/api/hooks";
import { useOrg } from "@/lib/auth/org-context";

export default function ChatLayout({ children }: { children: ReactNode }) {
  const { currentOrgId } = useOrg();
  const conversationsQuery = useConversations(currentOrgId);
  const createConversation = useCreateConversation(currentOrgId);
  const router = useRouter();
  const params = useParams<{ conversationId?: string }>();

  async function handleNewConversation() {
    const conversation = await createConversation.mutateAsync();
    router.push(`/chat/${conversation.id}`);
  }

  const conversations = conversationsQuery.data?.items ?? [];

  return (
    <div className="flex min-h-screen flex-1">
      <div className="flex w-72 shrink-0 flex-col border-r border-ink-100 bg-paper-dim/50">
        <div className="border-b border-ink-100 p-4">
          <button
            type="button"
            onClick={handleNewConversation}
            disabled={createConversation.isPending || currentOrgId === null}
            className="w-full rounded border border-ink-300 px-3 py-2 text-left text-sm font-medium text-ink-900 hover:border-ink-900"
          >
            + New conversation
          </button>
        </div>
        <ul className="flex-1 overflow-y-auto">
          {conversations.map((conversation) => {
            const isActive = params?.conversationId === conversation.id;
            return (
              <li key={conversation.id}>
                <Link
                  href={`/chat/${conversation.id}`}
                  className={`block truncate border-b border-ink-100/60 px-4 py-3 text-sm ${
                    isActive ? "bg-white font-medium text-ink-900" : "text-ink-500 hover:bg-white"
                  }`}
                >
                  {conversation.title ?? "New conversation"}
                </Link>
              </li>
            );
          })}
          {conversationsQuery.isSuccess && conversations.length === 0 && (
            <li className="px-4 py-6 text-sm text-ink-300">No conversations yet.</li>
          )}
        </ul>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}

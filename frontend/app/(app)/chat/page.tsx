export default function ChatIndexPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
      <h1 className="font-display text-xl font-semibold text-ink-900">Ask your knowledge base</h1>
      <p className="mt-2 max-w-sm text-sm text-ink-500">
        Start a new conversation to ask questions grounded in your organization&apos;s documents
        — every answer links back to its source.
      </p>
    </div>
  );
}

export function KeyValueList({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <p className="text-xs text-ink-300">—</p>;
  }
  return (
    <dl className="flex flex-col gap-1">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2 text-xs">
          <dt className="shrink-0 font-mono text-ink-300">{key}</dt>
          <dd className="min-w-0 break-words font-mono text-ink-700">
            {typeof value === "string" ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

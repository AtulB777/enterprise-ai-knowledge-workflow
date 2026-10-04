export function MetricCard({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: "danger" | "default";
}) {
  return (
    <div className="rounded-lg border border-ink-100 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p
        className={`mt-1 font-mono text-xl font-medium ${
          emphasis === "danger" ? "text-brick" : "text-ink-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

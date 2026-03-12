interface TimelineEntry {
  timestamp: string;
  type: string;
  summary: string;
}

interface TimelineProps {
  entries: TimelineEntry[];
}

const typeColors: Record<string, string> = {
  trade_executed: "bg-blue-500",
  regime_change: "bg-purple-500",
  belief_update: "bg-cyan-500",
  fee_accrual: "bg-zinc-500",
  subscription: "bg-green-500",
  redemption: "bg-red-500",
};

export function Timeline({ entries }: TimelineProps) {
  return (
    <div className="space-y-4">
      {entries.map((entry, i) => (
        <div key={i} className="flex gap-4 items-start">
          <div className="flex flex-col items-center">
            <div className={`w-2.5 h-2.5 rounded-full ${typeColors[entry.type] ?? "bg-zinc-600"}`} />
            {i < entries.length - 1 && <div className="w-px h-8 bg-zinc-800" />}
          </div>
          <div className="pb-6">
            <p className="text-sm text-white">{entry.summary}</p>
            <p className="text-xs text-zinc-600 mt-1">
              {new Date(entry.timestamp).toLocaleTimeString()} · {entry.type.replace("_", " ")}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

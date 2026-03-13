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
  fee_accrual: "bg-white/20",
  subscription: "bg-[#3dd68c]",
  redemption: "bg-[#f76e6e]",
};

export function Timeline({ entries }: TimelineProps) {
  return (
    <div className="space-y-4">
      {entries.map((entry, i) => (
        <div key={i} className="flex gap-4 items-start">
          <div className="flex flex-col items-center">
            <div className={`w-2 h-2 rounded-full ${typeColors[entry.type] ?? "bg-white/20"}`} />
            {i < entries.length - 1 && <div className="w-px h-8 bg-white/[0.06]" />}
          </div>
          <div className="pb-6">
            <p className="text-[13px] text-[#f5f5f5]">{entry.summary}</p>
            <p className="text-[11px] text-white/30 mt-1">
              {new Date(entry.timestamp).toLocaleTimeString()} · {entry.type.replace("_", " ")}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

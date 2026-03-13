"use client";
import { motion } from "framer-motion";

interface RaceEntry { name: string; returnPct: number; color: string; }
interface BenchmarkRaceProps { entries: RaceEntry[]; }

export function BenchmarkRace({ entries }: BenchmarkRaceProps) {
  const maxReturn = Math.max(...entries.map((e) => Math.abs(e.returnPct)), 1);

  return (
    <section className="py-24 max-w-4xl mx-auto px-6">
      <h2 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-12 text-center">The Race</h2>
      <div className="space-y-5">
        {entries.map((entry, i) => {
          const width = Math.max((entry.returnPct / maxReturn) * 100, 2);
          return (
            <div key={entry.name} className="flex items-center gap-4">
              <span className="text-[13px] text-white/65 w-32 text-right shrink-0">{entry.name}</span>
              <div className="flex-1 h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                <motion.div className="h-full rounded-full" style={{ backgroundColor: entry.color }}
                  initial={{ width: 0 }} whileInView={{ width: `${width}%` }}
                  transition={{ duration: 1.2, delay: i * 0.15, ease: "easeOut" }} viewport={{ once: true }} />
              </div>
              <span className="text-[13px] font-medium w-16" style={{ color: entry.color }}>
                {entry.returnPct > 0 ? "+" : ""}{entry.returnPct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

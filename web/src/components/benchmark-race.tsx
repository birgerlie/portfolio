"use client";
import { motion } from "framer-motion";

interface RaceEntry { name: string; returnPct: number; color: string; }
interface BenchmarkRaceProps { entries: RaceEntry[]; }

export function BenchmarkRace({ entries }: BenchmarkRaceProps) {
  const maxReturn = Math.max(...entries.map((e) => Math.abs(e.returnPct)), 1);

  return (
    <section className="py-24 max-w-4xl mx-auto px-6">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-12 text-center">The Race</h2>
      <div className="space-y-6">
        {entries.map((entry, i) => {
          const width = Math.max((entry.returnPct / maxReturn) * 100, 2);
          return (
            <div key={entry.name} className="flex items-center gap-4">
              <span className="text-sm text-zinc-400 w-32 text-right shrink-0">{entry.name}</span>
              <div className="flex-1 h-2 bg-zinc-900 rounded-full overflow-hidden">
                <motion.div className="h-full rounded-full" style={{ backgroundColor: entry.color }}
                  initial={{ width: 0 }} whileInView={{ width: `${width}%` }}
                  transition={{ duration: 1.2, delay: i * 0.15, ease: "easeOut" }} viewport={{ once: true }} />
              </div>
              <span className="text-sm font-medium w-16" style={{ color: entry.color }}>
                {entry.returnPct > 0 ? "+" : ""}{entry.returnPct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

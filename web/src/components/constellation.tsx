"use client";
import { motion } from "framer-motion";

interface Star { symbol: string; allocation: number; conviction: number; clarity: number; }
interface ConstellationProps { stars: Star[]; }

export function Constellation({ stars }: ConstellationProps) {
  if (stars.length === 0) return null;

  return (
    <section className="py-24 max-w-4xl mx-auto px-6">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-8 text-center">The Constellation</h2>
      <div className="relative w-full h-80 bg-zinc-950 rounded-2xl overflow-hidden border border-zinc-900">
        {/* Grid lines */}
        <div className="absolute inset-0 opacity-[0.07]"
          style={{ backgroundImage: "linear-gradient(to right, #71717a 1px, transparent 1px), linear-gradient(to bottom, #71717a 1px, transparent 1px)", backgroundSize: "20% 25%" }} />

        <span className="absolute bottom-3 right-4 text-[10px] text-zinc-600">Conviction &rarr;</span>
        <span className="absolute top-4 left-3 text-[10px] text-zinc-600 -rotate-90 origin-bottom-left">Clarity &rarr;</span>

        {stars.map((star, i) => {
          const x = 8 + star.conviction * 84;
          const y = 88 - star.clarity * 76;
          const size = 20 + star.allocation * 60;
          return (
            <motion.div key={star.symbol}
              className="absolute flex flex-col items-center justify-center"
              style={{ left: `${x}%`, top: `${y}%`, transform: "translate(-50%, -50%)" }}
              initial={{ opacity: 0, scale: 0 }} whileInView={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.12, duration: 0.6, type: "spring" }} viewport={{ once: true }}
              title={`${star.symbol}: ${(star.allocation * 100).toFixed(0)}% allocation`}>
              <div className="rounded-full bg-blue-500/15 border border-blue-400/30 flex items-center justify-center backdrop-blur-sm"
                style={{ width: size, height: size, boxShadow: "0 0 20px rgba(59,130,246,0.15)" }}>
                <span className="text-[11px] text-blue-300 font-semibold tracking-wide">{star.symbol}</span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

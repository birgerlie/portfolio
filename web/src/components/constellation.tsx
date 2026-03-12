"use client";
import { motion } from "framer-motion";

interface Star { symbol: string; allocation: number; conviction: number; clarity: number; }
interface ConstellationProps { stars: Star[]; }

export function Constellation({ stars }: ConstellationProps) {
  return (
    <section className="py-24 max-w-4xl mx-auto px-6">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-8 text-center">The Constellation</h2>
      <div className="relative w-full h-80 bg-zinc-950 rounded-2xl overflow-hidden border border-zinc-900">
        <span className="absolute bottom-2 right-4 text-[10px] text-zinc-700">Conviction →</span>
        <span className="absolute top-4 left-2 text-[10px] text-zinc-700 -rotate-90 origin-bottom-left">Clarity →</span>
        {stars.map((star, i) => {
          const x = 10 + star.conviction * 80;
          const y = 90 - star.clarity * 80;
          const size = 16 + star.allocation * 48;
          return (
            <motion.div key={star.symbol}
              className="absolute flex items-center justify-center rounded-full bg-blue-500/20 border border-blue-500/40"
              style={{ left: `${x}%`, top: `${y}%`, width: size, height: size, transform: "translate(-50%, -50%)" }}
              initial={{ opacity: 0, scale: 0 }} whileInView={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1, duration: 0.5 }} viewport={{ once: true }}
              title={`${star.symbol}: ${(star.allocation * 100).toFixed(0)}% allocation`}>
              <span className="text-[10px] text-blue-300 font-medium">{star.symbol}</span>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

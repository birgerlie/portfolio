"use client";

import { motion } from "framer-motion";

interface RingProps {
  value: number;
  color: string;
  label: string;
  size: number;
  delay: number;
}

function Ring({ value, color, label, size, delay }: RingProps) {
  const radius = size / 2 - 8;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - value);

  return (
    <div className="flex flex-col items-center gap-3">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.06)" strokeWidth={6} fill="none" />
        <motion.circle
          cx={size / 2} cy={size / 2} r={radius} stroke={color} strokeWidth={6} fill="none"
          strokeLinecap="round" strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          whileInView={{ strokeDashoffset }}
          transition={{ duration: 1.5, delay, ease: "easeOut" }}
          viewport={{ once: true }}
        />
      </svg>
      <motion.div className="text-center" initial={{ opacity: 0 }} whileInView={{ opacity: 1 }}
        transition={{ delay: delay + 1, duration: 0.5 }} viewport={{ once: true }}>
        <p className="text-xl font-medium tracking-tight">{Math.round(value * 100)}%</p>
        <p className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">{label}</p>
      </motion.div>
    </div>
  );
}

interface ActivityRingsProps {
  clarity: number;
  opportunity: number;
  marketHealth: string;
}

export function ActivityRings({ clarity, opportunity, marketHealth }: ActivityRingsProps) {
  const healthValue = marketHealth === "green" ? 0.9 : marketHealth === "yellow" ? 0.5 : 0.2;
  const healthColor = marketHealth === "green" ? "#3dd68c" : marketHealth === "yellow" ? "#eab308" : "#f76e6e";

  return (
    <section className="py-32 flex justify-center gap-16 md:gap-24">
      <Ring value={clarity / 100} color="#3b82f6" label="Clarity" size={140} delay={0} />
      <Ring value={opportunity / 100} color="#a855f7" label="Opportunity" size={140} delay={0.2} />
      <Ring value={healthValue} color={healthColor} label="Market Health" size={140} delay={0.4} />
    </section>
  );
}

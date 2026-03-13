"use client";

import { motion, useSpring, useTransform } from "framer-motion";
import { useEffect } from "react";

interface HeroProps {
  currentValue: number;
  returnPct: number;
  currency?: string;
}

export function Hero({ currentValue, returnPct, currency = "€" }: HeroProps) {
  const spring = useSpring(0, { stiffness: 50, damping: 20 });
  const display = useTransform(spring, (v) =>
    `${currency}${Math.round(v).toLocaleString()}`
  );

  useEffect(() => {
    spring.set(currentValue);
  }, [currentValue, spring]);

  return (
    <section className="min-h-screen flex flex-col items-center justify-center relative">
      <motion.h1
        className="text-7xl md:text-9xl font-medium tracking-tighter text-[#f5f5f5]"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1, ease: "easeOut" }}
      >
        <motion.span>{display}</motion.span>
      </motion.h1>
      <motion.p
        className={`mt-4 text-lg ${returnPct >= 0 ? "text-[#3dd68c]" : "text-[#f76e6e]"}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5, duration: 0.8 }}
      >
        {returnPct >= 0 ? "↑" : "↓"} {Math.abs(returnPct).toFixed(1)}% since you joined
      </motion.p>
    </section>
  );
}

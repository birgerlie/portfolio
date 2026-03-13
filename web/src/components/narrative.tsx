"use client";
import { motion } from "framer-motion";

interface NarrativeProps { text: string; }

export function Narrative({ text }: NarrativeProps) {
  return (
    <section className="py-32 max-w-3xl mx-auto px-6">
      <motion.blockquote
        className="text-xl md:text-2xl font-medium tracking-tight leading-relaxed text-white/90 text-center"
        initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }} viewport={{ once: true }}>
        &ldquo;{text}&rdquo;
      </motion.blockquote>
    </section>
  );
}

"use client";

import { useState } from "react";

export default function RedeemPage() {
  const [units, setUnits] = useState("");
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const res = await fetch("/api/redeem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ units: parseFloat(units) }),
    });
    if (res.ok) setSubmitted(true);
  }

  if (submitted) {
    return (
      <div className="min-h-screen pt-24 px-6 text-center">
        <h2 className="text-xl font-medium tracking-tight mb-4">Redemption Requested</h2>
        <p className="text-white/65 text-[13px]">Your request for {units} units will be processed at the next monthly window.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen pt-24 px-6 max-w-sm mx-auto">
      <h1 className="text-2xl font-medium tracking-tight text-center mb-1">Redeem</h1>
      <p className="text-white/40 text-[13px] text-center mb-12">Request a redemption</p>
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium block mb-2">Units to redeem</label>
          <input type="number" min="0.01" step="0.01" value={units} onChange={(e) => setUnits(e.target.value)} required
            className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-4 py-3 text-[#f5f5f5] text-xl font-medium tracking-tight text-center focus:outline-none focus:border-white/[0.12] transition-colors" />
        </div>
        <button type="submit" className="w-full bg-white text-[#0a0a0a] rounded-lg py-3 text-[13px] font-medium hover:bg-white/90 transition-colors">Submit Redemption Request</button>
        <p className="text-[11px] text-white/30 text-center">1-month notice. 3-month lock-up applies.</p>
      </form>
    </div>
  );
}

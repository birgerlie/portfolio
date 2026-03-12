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
      <div className="min-h-screen pt-28 px-6 text-center">
        <h2 className="text-3xl font-light mb-4">Redemption Requested</h2>
        <p className="text-zinc-400">Your request for {units} units will be processed at the next monthly window.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen pt-28 px-6 max-w-sm mx-auto">
      <h1 className="text-4xl font-light text-center mb-2">Redeem</h1>
      <p className="text-zinc-500 text-center mb-12">Request a redemption</p>
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="text-sm text-zinc-400 block mb-2">Units to redeem</label>
          <input type="number" min="0.01" step="0.01" value={units} onChange={(e) => setUnits(e.target.value)} required
            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-white text-2xl font-light text-center focus:outline-none focus:border-zinc-600" />
        </div>
        <button type="submit" className="w-full bg-white text-black rounded-lg py-3 font-medium hover:bg-zinc-200 transition-colors">Submit Redemption Request</button>
        <p className="text-xs text-zinc-600 text-center">1-month notice. 3-month lock-up applies.</p>
      </form>
    </div>
  );
}

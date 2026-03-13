"use client";

import { useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useStripe, useElements } from "@stripe/react-stripe-js";

const stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!);

function InvestForm() {
  const [amount, setAmount] = useState("");
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<"amount" | "payment" | "success">("amount");

  async function handleSubmitAmount(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const res = await fetch("/api/create-payment-intent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount: parseFloat(amount) }),
    });
    const data = await res.json();
    setClientSecret(data.clientSecret);
    setStep("payment");
    setLoading(false);
  }

  if (step === "success") {
    return (
      <div className="text-center">
        <h2 className="text-xl font-medium tracking-tight mb-4">Investment Submitted</h2>
        <p className="text-white/65 text-[13px]">
          Your €{parseFloat(amount).toLocaleString()} investment will be processed at the next monthly subscription window.
        </p>
      </div>
    );
  }

  if (step === "payment" && clientSecret) {
    return (
      <Elements stripe={stripePromise} options={{ clientSecret, appearance: { theme: "night" } }}>
        <PaymentForm onSuccess={() => setStep("success")} />
      </Elements>
    );
  }

  return (
    <form onSubmit={handleSubmitAmount} className="space-y-6 max-w-sm mx-auto">
      <div>
        <label className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium block mb-2">Investment Amount (EUR)</label>
        <input type="number" min="100" step="100" value={amount} onChange={(e) => setAmount(e.target.value)}
          placeholder="10,000" required
          className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-4 py-3 text-[#f5f5f5] text-xl font-medium tracking-tight text-center focus:outline-none focus:border-white/[0.12] transition-colors" />
      </div>
      <button type="submit" disabled={loading}
        className="w-full bg-white text-[#0a0a0a] rounded-lg py-3 text-[13px] font-medium hover:bg-white/90 transition-colors disabled:opacity-50">
        {loading ? "Preparing..." : "Continue to Payment"}
      </button>
      <p className="text-[11px] text-white/30 text-center">Funds held until next monthly window. Minimum €100.</p>
    </form>
  );
}

function PaymentForm({ onSuccess }: { onSuccess: () => void }) {
  const stripe = useStripe();
  const elements = useElements();
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;
    setLoading(true);
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: `${window.location.origin}/invest` },
      redirect: "if_required",
    });
    if (error) setLoading(false);
    else onSuccess();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-sm mx-auto">
      <PaymentElement />
      <button type="submit" disabled={loading || !stripe}
        className="w-full bg-white text-[#0a0a0a] rounded-lg py-3 text-[13px] font-medium hover:bg-white/90 transition-colors disabled:opacity-50">
        {loading ? "Processing..." : "Confirm Investment"}
      </button>
    </form>
  );
}

export default function InvestPage() {
  return (
    <div className="min-h-screen pt-24 px-6">
      <h1 className="text-2xl font-medium tracking-tight text-center mb-1">Invest</h1>
      <p className="text-white/40 text-[13px] text-center mb-12">Subscribe to the fund</p>
      <InvestForm />
    </div>
  );
}

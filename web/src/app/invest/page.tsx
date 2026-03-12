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
        <h2 className="text-3xl font-light mb-4">Investment Submitted</h2>
        <p className="text-zinc-400">
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
        <label className="text-sm text-zinc-400 block mb-2">Investment Amount (EUR)</label>
        <input type="number" min="100" step="100" value={amount} onChange={(e) => setAmount(e.target.value)}
          placeholder="10,000" required
          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-white text-2xl font-light text-center focus:outline-none focus:border-zinc-600" />
      </div>
      <button type="submit" disabled={loading}
        className="w-full bg-white text-black rounded-lg py-3 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-50">
        {loading ? "Preparing..." : "Continue to Payment"}
      </button>
      <p className="text-xs text-zinc-600 text-center">Funds held until next monthly window. Minimum €100.</p>
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
        className="w-full bg-white text-black rounded-lg py-3 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-50">
        {loading ? "Processing..." : "Confirm Investment"}
      </button>
    </form>
  );
}

export default function InvestPage() {
  return (
    <div className="min-h-screen pt-28 px-6">
      <h1 className="text-4xl font-light text-center mb-2">Invest</h1>
      <p className="text-zinc-500 text-center mb-12">Subscribe to the fund</p>
      <InvestForm />
    </div>
  );
}

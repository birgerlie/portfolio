"use client";

import { useState } from "react";
import { createSupabaseBrowser } from "@/lib/supabase-client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const supabase = createSupabaseBrowser();
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) {
      setError(error.message);
    } else {
      setSent(true);
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
      <div className="w-full max-w-sm px-8">
        <h1 className="text-2xl font-medium tracking-tight text-[#f5f5f5] text-center mb-1">
          Glass Box Fund
        </h1>
        <p className="text-white/40 text-center mb-12 text-[13px]">
          Investment Club Dashboard
        </p>

        {sent ? (
          <div className="text-center">
            <p className="text-[#f5f5f5] text-[15px] mb-2">Check your email</p>
            <p className="text-white/65 text-[13px]">
              We sent a magic link to <span className="text-[#f5f5f5]">{email}</span>
            </p>
          </div>
        ) : (
          <form onSubmit={handleLogin} className="space-y-4">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-4 py-3 text-[#f5f5f5] text-[13px] placeholder-white/30 focus:outline-none focus:border-white/[0.12] transition-colors"
            />
            <button
              type="submit"
              className="w-full bg-white text-[#0a0a0a] rounded-lg py-3 text-[13px] font-medium hover:bg-white/90 transition-colors"
            >
              Sign in with magic link
            </button>
            {error && (
              <p className="text-[#f76e6e] text-[13px] text-center">{error}</p>
            )}
          </form>
        )}
      </div>
    </div>
  );
}

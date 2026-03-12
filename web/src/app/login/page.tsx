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
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="w-full max-w-sm px-8">
        <h1 className="text-4xl font-light text-white text-center mb-2">
          Glass Box Fund
        </h1>
        <p className="text-zinc-500 text-center mb-12 text-sm">
          Investment Club Dashboard
        </p>

        {sent ? (
          <div className="text-center">
            <p className="text-white text-lg mb-2">Check your email</p>
            <p className="text-zinc-400 text-sm">
              We sent a magic link to <span className="text-white">{email}</span>
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
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
            />
            <button
              type="submit"
              className="w-full bg-white text-black rounded-lg py-3 font-medium hover:bg-zinc-200 transition-colors"
            >
              Sign in with magic link
            </button>
            {error && (
              <p className="text-red-400 text-sm text-center">{error}</p>
            )}
          </form>
        )}
      </div>
    </div>
  );
}

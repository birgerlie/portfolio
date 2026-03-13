"use client";

import { useEffect, useState } from "react";

interface Member {
  id: string;
  name: string;
  email: string;
  role: string;
  units: number;
  costBasis: number;
  joinDate: string;
  _count: { transactions: number };
}

interface FundStats {
  fund: {
    nav: number;
    navPerUnit: number;
    unitsOutstanding: number;
    cash: number;
    highWaterMark: number;
    positionsCount: number;
    date: string | null;
  };
  capital: {
    totalInvested: number;
    totalRedeemed: number;
    netInvested: number;
    totalUnits: number;
    totalCostBasis: number;
    memberCount: number;
  };
  fees: {
    realizedMgmt: number;
    realizedPerf: number;
    realizedTotal: number;
    accruedMgmt: number;
    accruedPerf: number;
    accruedTotal: number;
    grandTotal: number;
  };
  transactions: {
    total: number;
    completed: number;
    pending: number;
  };
}

function fmt(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(2)}%`;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className="text-xl font-light text-zinc-100">{value}</p>
      {sub && <p className="text-xs text-zinc-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function AdminPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [stats, setStats] = useState<FundStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState("");

  const [liquidateStep, setLiquidateStep] = useState<"idle" | "confirm" | "typing" | "executing" | "done">("idle");
  const [liquidateConfirm, setLiquidateConfirm] = useState("");
  const [liquidateResult, setLiquidateResult] = useState("");

  async function fetchAll() {
    const [membersRes, statsRes] = await Promise.all([
      fetch("/api/admin/members"),
      fetch("/api/admin/stats"),
    ]);
    if (membersRes.ok) setMembers(await membersRes.json());
    if (statsRes.ok) setStats(await statsRes.json());
    setLoading(false);
  }

  useEffect(() => { fetchAll(); }, []);

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setInviteMsg("");
    const res = await fetch("/api/admin/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: inviteEmail, name: inviteName }),
    });
    const data = await res.json();
    if (res.ok) {
      setInviteMsg(`Magic link sent to ${inviteEmail}`);
      setInviteEmail("");
      setInviteName("");
    } else {
      setInviteMsg(`Error: ${data.error}`);
    }
    setInviting(false);
  }

  async function toggleRole(member: Member) {
    const newRole = member.role === "admin" ? "member" : "admin";
    await fetch("/api/admin/members", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: member.id, role: newRole }),
    });
    fetchAll();
  }

  async function removeMember(member: Member) {
    if (!confirm(`Remove ${member.name} (${member.email})?`)) return;
    await fetch("/api/admin/members", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: member.id }),
    });
    fetchAll();
  }

  async function executeLiquidation() {
    setLiquidateStep("executing");
    const res = await fetch("/api/admin/liquidate", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      setLiquidateResult(`Liquidated ${data.closed} positions. All orders cancelled.`);
    } else {
      setLiquidateResult(`Error: ${data.error}`);
    }
    setLiquidateStep("done");
    setLiquidateConfirm("");
    fetchAll();
  }

  if (loading) return <div className="min-h-screen pt-28 px-6 max-w-5xl mx-auto"><p className="text-zinc-500">Loading...</p></div>;
  if (error) return <div className="min-h-screen pt-28 px-6 max-w-5xl mx-auto"><p className="text-red-400">{error}</p></div>;

  const unrealizedGain = stats ? stats.fund.nav - stats.capital.totalCostBasis : 0;
  const unrealizedPct = stats && stats.capital.totalCostBasis > 0 ? unrealizedGain / stats.capital.totalCostBasis : 0;

  return (
    <div className="min-h-screen pt-28 px-6 max-w-5xl mx-auto pb-20">
      <h1 className="text-4xl font-light mb-2">Admin</h1>
      <p className="text-zinc-500 mb-10">Fund overview, fees, and member management</p>

      {/* Fund Overview */}
      {stats && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-5">
              <Stat label="Net Asset Value" value={fmt(stats.fund.nav)} sub={`${stats.fund.positionsCount} positions`} />
            </div>
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-5">
              <Stat label="NAV / Unit" value={`$${stats.fund.navPerUnit.toFixed(2)}`} sub={`HWM $${stats.fund.highWaterMark.toFixed(2)}`} />
            </div>
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-5">
              <Stat label="Cash" value={fmt(stats.fund.cash)} sub={stats.fund.nav > 0 ? `${((stats.fund.cash / stats.fund.nav) * 100).toFixed(1)}% of NAV` : undefined} />
            </div>
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-5">
              <Stat
                label="Unrealized P&L"
                value={fmt(unrealizedGain)}
                sub={stats.capital.totalCostBasis > 0 ? fmtPct(unrealizedPct) : undefined}
              />
            </div>
          </div>

          {/* Capital & Fees */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
            {/* Capital */}
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-5">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-4">Capital</h3>
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Total Invested" value={fmt(stats.capital.totalInvested)} />
                <Stat label="Total Redeemed" value={fmt(stats.capital.totalRedeemed)} />
                <Stat label="Net Invested" value={fmt(stats.capital.netInvested)} />
                <Stat label="Cost Basis" value={fmt(stats.capital.totalCostBasis)} />
                <Stat label="Units Outstanding" value={stats.fund.unitsOutstanding.toFixed(2)} />
                <Stat label="Members" value={String(stats.capital.memberCount)} />
              </div>
            </div>

            {/* Fees / Admin Earnings */}
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-5">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-4">Admin Earnings (Fees)</h3>
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Management (realized)" value={fmt(stats.fees.realizedMgmt)} />
                <Stat label="Performance (realized)" value={fmt(stats.fees.realizedPerf)} />
                <Stat label="Management (accrued)" value={fmt(stats.fees.accruedMgmt)} />
                <Stat label="Performance (accrued)" value={fmt(stats.fees.accruedPerf)} />
              </div>
              <div className="mt-4 pt-4 border-t border-zinc-800 flex justify-between items-end">
                <div>
                  <p className="text-xs text-zinc-500">Total Earned</p>
                  <p className="text-2xl font-light text-emerald-400">{fmt(stats.fees.grandTotal)}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-zinc-500">Transactions</p>
                  <p className="text-sm text-zinc-300">{stats.transactions.completed} settled · {stats.transactions.pending} pending</p>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Invite Section */}
      <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-6 mb-10">
        <h2 className="text-lg font-medium mb-4">Send Magic Link</h2>
        <form onSubmit={sendInvite} className="flex flex-col sm:flex-row gap-3">
          <input
            type="email" required placeholder="Email address" value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          />
          <input
            type="text" placeholder="Name (optional)" value={inviteName}
            onChange={(e) => setInviteName(e.target.value)}
            className="sm:w-48 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          />
          <button type="submit" disabled={inviting}
            className="bg-white text-black px-6 py-2 rounded-lg text-sm font-medium hover:bg-zinc-200 transition-colors disabled:opacity-50">
            {inviting ? "Sending..." : "Send Invite"}
          </button>
        </form>
        {inviteMsg && (
          <p className={`mt-3 text-sm ${inviteMsg.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
            {inviteMsg}
          </p>
        )}
      </div>

      {/* Emergency Liquidation */}
      <div className="bg-red-950/20 rounded-xl border border-red-900/30 p-6 mb-10">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-medium text-red-400">Emergency Liquidation</h2>
            <p className="text-sm text-zinc-500 mt-1">Cancel all orders and close all positions at market price</p>
          </div>

          {liquidateStep === "idle" && (
            <button
              onClick={() => setLiquidateStep("confirm")}
              className="bg-red-600 hover:bg-red-500 text-white px-8 py-3 rounded-lg text-sm font-medium transition-colors"
            >
              Sell Everything
            </button>
          )}

          {liquidateStep === "confirm" && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-red-400">Are you sure?</span>
              <button
                onClick={() => setLiquidateStep("typing")}
                className="bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                Yes, proceed
              </button>
              <button
                onClick={() => setLiquidateStep("idle")}
                className="text-sm text-zinc-500 hover:text-white transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {liquidateStep === "typing" && (
            <div className="flex items-center gap-3">
              <div>
                <p className="text-xs text-red-400 mb-1">Type LIQUIDATE to confirm</p>
                <input
                  type="text"
                  value={liquidateConfirm}
                  onChange={(e) => setLiquidateConfirm(e.target.value)}
                  autoFocus
                  className="bg-zinc-900 border border-red-800 rounded-lg px-4 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-red-500 w-40"
                  placeholder="LIQUIDATE"
                />
              </div>
              <button
                onClick={executeLiquidation}
                disabled={liquidateConfirm !== "LIQUIDATE"}
                className="bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Confirm
              </button>
              <button
                onClick={() => { setLiquidateStep("idle"); setLiquidateConfirm(""); }}
                className="text-sm text-zinc-500 hover:text-white transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {liquidateStep === "executing" && (
            <p className="text-sm text-yellow-400 animate-pulse">Liquidating all positions...</p>
          )}
        </div>

        {liquidateStep === "done" && liquidateResult && (
          <p className={`mt-4 text-sm ${liquidateResult.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
            {liquidateResult}
          </p>
        )}
      </div>

      {/* Members Table */}
      <h2 className="text-lg font-medium mb-4">Members ({members.length})</h2>
      {members.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-3 font-normal">Name</th>
                <th className="text-left py-3 font-normal">Email</th>
                <th className="text-left py-3 font-normal">Role</th>
                <th className="text-right py-3 font-normal">Units</th>
                <th className="text-right py-3 font-normal">Cost Basis</th>
                <th className="text-right py-3 font-normal">Txns</th>
                <th className="text-right py-3 font-normal">Joined</th>
                <th className="text-right py-3 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id} className="border-b border-zinc-800/50">
                  <td className="py-3 font-medium">{m.name}</td>
                  <td className="py-3 text-zinc-400">{m.email}</td>
                  <td className="py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${m.role === "admin" ? "bg-blue-500/20 text-blue-400" : "bg-zinc-800 text-zinc-400"}`}>
                      {m.role}
                    </span>
                  </td>
                  <td className="text-right py-3 text-zinc-400">{m.units.toFixed(2)}</td>
                  <td className="text-right py-3 text-zinc-400">{fmt(m.costBasis)}</td>
                  <td className="text-right py-3 text-zinc-400">{m._count.transactions}</td>
                  <td className="text-right py-3 text-zinc-500">{new Date(m.joinDate).toLocaleDateString()}</td>
                  <td className="text-right py-3 space-x-2">
                    <button onClick={() => toggleRole(m)} className="text-xs text-zinc-500 hover:text-white transition-colors">
                      {m.role === "admin" ? "Demote" : "Promote"}
                    </button>
                    <button onClick={() => removeMember(m)} className="text-xs text-zinc-500 hover:text-red-400 transition-colors">
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-zinc-600">No members yet. Send an invite to get started.</p>
      )}
    </div>
  );
}

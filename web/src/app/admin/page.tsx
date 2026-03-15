"use client";

import { useEffect, useState } from "react";

interface Invite {
  id: string;
  email: string;
  name: string;
  status: string;
  sentAt: string;
  acceptedAt: string | null;
}

interface Member {
  id: string;
  name: string;
  email: string;
  role: string;
  units: number;
  costBasis: number;
  joinDate: string;
  totalInvested: number;
  totalRedeemed: number;
  investmentCount: number;
  redemptionCount: number;
  pendingRedemptions: number;
  pendingRedemptionAmount: number;
  lastActivity: string | null;
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
      <p className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-1.5">{label}</p>
      <p className="text-xl font-medium tracking-tight text-[#f5f5f5]">{value}</p>
      {sub && <p className="text-[11px] text-white/30 mt-0.5">{sub}</p>}
    </div>
  );
}

function StatusBadge({ status, children }: { status: "green" | "yellow" | "red" | "neutral"; children: React.ReactNode }) {
  const colors = {
    green: "bg-[#3dd68c]/10 text-[#3dd68c]",
    yellow: "bg-yellow-400/10 text-yellow-400",
    red: "bg-[#f76e6e]/10 text-[#f76e6e]",
    neutral: "bg-white/[0.06] text-white/40",
  };
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-lg ${colors[status]}`}>
      {children}
    </span>
  );
}

export default function AdminPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
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
    const [membersRes, statsRes, invitesRes] = await Promise.all([
      fetch("/api/admin/members"),
      fetch("/api/admin/stats"),
      fetch("/api/admin/invite"),
    ]);
    if (membersRes.ok) setMembers(await membersRes.json());
    if (statsRes.ok) setStats(await statsRes.json());
    if (invitesRes.ok) setInvites(await invitesRes.json());
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
      fetchAll();
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

  if (loading) return <div className="min-h-screen pt-24 px-6 max-w-5xl mx-auto"><p className="text-white/40">Loading...</p></div>;
  if (error) return <div className="min-h-screen pt-24 px-6 max-w-5xl mx-auto"><p className="text-[#f76e6e]">{error}</p></div>;

  const unrealizedGain = stats ? stats.fund.nav - stats.capital.totalCostBasis : 0;
  const unrealizedPct = stats && stats.capital.totalCostBasis > 0 ? unrealizedGain / stats.capital.totalCostBasis : 0;
  const pendingInvites = invites.filter((i) => i.status === "pending");

  return (
    <div className="min-h-screen pt-24 px-6 max-w-5xl mx-auto pb-20">
      <h1 className="text-2xl font-medium tracking-tight mb-1">Admin</h1>
      <p className="text-white/40 text-[13px] mb-10">Fund overview, member management, and controls</p>

      {/* Fund Overview */}
      {stats && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/[0.04] rounded-lg overflow-hidden mb-6">
            <div className="bg-[#0a0a0a] p-4">
              <Stat label="Net Asset Value" value={fmt(stats.fund.nav)} sub={`${stats.fund.positionsCount} positions`} />
            </div>
            <div className="bg-[#0a0a0a] p-4">
              <Stat label="NAV / Unit" value={`$${stats.fund.navPerUnit.toFixed(2)}`} sub={`HWM $${stats.fund.highWaterMark.toFixed(2)}`} />
            </div>
            <div className="bg-[#0a0a0a] p-4">
              <Stat label="Cash" value={fmt(stats.fund.cash)} sub={stats.fund.nav > 0 ? `${((stats.fund.cash / stats.fund.nav) * 100).toFixed(1)}% of NAV` : undefined} />
            </div>
            <div className="bg-[#0a0a0a] p-4">
              <Stat
                label="Unrealized P&L"
                value={fmt(unrealizedGain)}
                sub={stats.capital.totalCostBasis > 0 ? fmtPct(unrealizedPct) : undefined}
              />
            </div>
          </div>

          {/* Capital & Fees */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-10">
            <div className="border border-white/[0.06] rounded-lg p-5">
              <h3 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-4">Capital</h3>
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Total Invested" value={fmt(stats.capital.totalInvested)} />
                <Stat label="Total Redeemed" value={fmt(stats.capital.totalRedeemed)} />
                <Stat label="Net Invested" value={fmt(stats.capital.netInvested)} />
                <Stat label="Cost Basis" value={fmt(stats.capital.totalCostBasis)} />
                <Stat label="Units Outstanding" value={stats.fund.unitsOutstanding.toFixed(2)} />
                <Stat label="Members" value={String(stats.capital.memberCount)} />
              </div>
            </div>

            <div className="border border-white/[0.06] rounded-lg p-5">
              <h3 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-4">Admin Earnings (Fees)</h3>
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Management (realized)" value={fmt(stats.fees.realizedMgmt)} />
                <Stat label="Performance (realized)" value={fmt(stats.fees.realizedPerf)} />
                <Stat label="Management (accrued)" value={fmt(stats.fees.accruedMgmt)} />
                <Stat label="Performance (accrued)" value={fmt(stats.fees.accruedPerf)} />
              </div>
              <div className="mt-4 pt-4 border-t border-white/[0.06] flex justify-between items-end">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Total Earned</p>
                  <p className="text-xl font-medium tracking-tight text-[#3dd68c]">{fmt(stats.fees.grandTotal)}</p>
                </div>
                <div className="text-right">
                  <p className="text-[11px] text-white/40">Transactions</p>
                  <p className="text-[13px] text-white/65">{stats.transactions.completed} settled · {stats.transactions.pending} pending</p>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Invite Section */}
      <div className="border border-white/[0.06] rounded-lg p-5 mb-6">
        <h2 className="text-[13px] font-medium text-[#f5f5f5] mb-4">Invite Member</h2>
        <form onSubmit={sendInvite} className="flex flex-col sm:flex-row gap-3">
          <input
            type="email" required placeholder="Email address" value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            className="flex-1 bg-white/[0.03] border border-white/[0.06] rounded-lg px-4 py-2.5 text-[13px] text-[#f5f5f5] placeholder-white/30 focus:outline-none focus:border-white/[0.12] transition-colors"
          />
          <input
            type="text" placeholder="Name (optional)" value={inviteName}
            onChange={(e) => setInviteName(e.target.value)}
            className="sm:w-48 bg-white/[0.03] border border-white/[0.06] rounded-lg px-4 py-2.5 text-[13px] text-[#f5f5f5] placeholder-white/30 focus:outline-none focus:border-white/[0.12] transition-colors"
          />
          <button type="submit" disabled={inviting}
            className="bg-white text-[#0a0a0a] px-6 py-2.5 rounded-lg text-[13px] font-medium hover:bg-white/90 transition-colors disabled:opacity-50">
            {inviting ? "Sending..." : "Send Magic Link"}
          </button>
        </form>
        {inviteMsg && (
          <p className={`mt-3 text-[13px] ${inviteMsg.startsWith("Error") ? "text-[#f76e6e]" : "text-[#3dd68c]"}`}>
            {inviteMsg}
          </p>
        )}
      </div>

      {/* Pending Invites */}
      {pendingInvites.length > 0 && (
        <div className="border border-white/[0.06] rounded-lg overflow-hidden mb-10">
          <div className="px-4 py-3 border-b border-white/[0.06]">
            <h3 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">
              Pending Invites ({pendingInvites.length})
            </h3>
          </div>
          <table className="w-full text-[13px]">
            <tbody>
              {pendingInvites.map((inv) => (
                <tr key={inv.id} className="border-b border-white/[0.03] last:border-b-0">
                  <td className="py-2.5 px-4 text-white/65">{inv.email}</td>
                  <td className="py-2.5 px-4 text-white/40">{inv.name || "—"}</td>
                  <td className="py-2.5 px-4">
                    <StatusBadge status="yellow">Awaiting signup</StatusBadge>
                  </td>
                  <td className="text-right py-2.5 px-4 text-white/30 text-[11px]">
                    Sent {new Date(inv.sentAt).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Members Table */}
      <h2 className="text-[13px] font-medium text-[#f5f5f5] mb-4">Members ({members.length})</h2>
      {members.length > 0 ? (
        <div className="border border-white/[0.06] rounded-lg overflow-hidden mb-10">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="text-left py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Name</th>
                  <th className="text-left py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Email</th>
                  <th className="text-left py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Role</th>
                  <th className="text-left py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Status</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Invested</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Units</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Redemptions</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Joined</th>
                  <th className="text-right py-2.5 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => {
                  const hasInvested = m.totalInvested > 0;
                  const hasPendingRedeem = m.pendingRedemptions > 0;

                  return (
                    <tr key={m.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                      <td className="py-2.5 px-4 font-medium text-[#f5f5f5]">{m.name}</td>
                      <td className="py-2.5 px-4 text-white/65">{m.email}</td>
                      <td className="py-2.5 px-4">
                        <span className={`text-[11px] px-2 py-0.5 rounded-lg ${m.role === "admin" ? "bg-blue-500/10 text-blue-400" : "bg-white/[0.06] text-white/40"}`}>
                          {m.role}
                        </span>
                      </td>
                      <td className="py-2.5 px-4">
                        {hasPendingRedeem ? (
                          <StatusBadge status="red">Sell pending</StatusBadge>
                        ) : hasInvested ? (
                          <StatusBadge status="green">Active</StatusBadge>
                        ) : (
                          <StatusBadge status="neutral">No investment</StatusBadge>
                        )}
                      </td>
                      <td className="text-right py-2.5 px-4">
                        {hasInvested ? (
                          <span className="text-[#f5f5f5]">
                            {fmt(m.totalInvested)}
                            <span className="text-white/30 ml-1 text-[11px]">({m.investmentCount}x)</span>
                          </span>
                        ) : (
                          <span className="text-white/30">—</span>
                        )}
                      </td>
                      <td className="text-right py-2.5 px-4 text-white/65">{m.units > 0 ? m.units.toFixed(2) : "—"}</td>
                      <td className="text-right py-2.5 px-4">
                        {m.totalRedeemed > 0 || hasPendingRedeem ? (
                          <span>
                            {m.totalRedeemed > 0 && (
                              <span className="text-white/65">{fmt(m.totalRedeemed)}</span>
                            )}
                            {hasPendingRedeem && (
                              <span className="text-[#f76e6e] ml-1 text-[11px]">
                                +{fmt(m.pendingRedemptionAmount)} pending
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="text-white/30">—</span>
                        )}
                      </td>
                      <td className="text-right py-2.5 px-4 text-white/40">{new Date(m.joinDate).toLocaleDateString()}</td>
                      <td className="text-right py-2.5 px-4 space-x-2">
                        <button onClick={() => toggleRole(m)} className="text-[11px] text-white/40 hover:text-white/90 transition-colors">
                          {m.role === "admin" ? "Demote" : "Promote"}
                        </button>
                        <button onClick={() => removeMember(m)} className="text-[11px] text-white/40 hover:text-[#f76e6e] transition-colors">
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="text-white/30 text-[13px] mb-10">No members yet. Send an invite to get started.</p>
      )}

      {/* Emergency Liquidation */}
      <div className="border border-[#f76e6e]/20 rounded-lg p-5 bg-[#f76e6e]/[0.03]">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[13px] font-medium text-[#f76e6e]">Emergency Liquidation</h2>
            <p className="text-[11px] text-white/40 mt-1">Cancel all orders and close all positions at market price</p>
          </div>

          {liquidateStep === "idle" && (
            <button
              onClick={() => setLiquidateStep("confirm")}
              className="bg-[#f76e6e]/20 hover:bg-[#f76e6e]/30 text-[#f76e6e] border border-[#f76e6e]/20 px-6 py-2.5 rounded-lg text-[13px] font-medium transition-colors"
            >
              Sell Everything
            </button>
          )}

          {liquidateStep === "confirm" && (
            <div className="flex items-center gap-3">
              <span className="text-[13px] text-[#f76e6e]">Are you sure?</span>
              <button
                onClick={() => setLiquidateStep("typing")}
                className="bg-[#f76e6e]/20 hover:bg-[#f76e6e]/30 text-[#f76e6e] border border-[#f76e6e]/20 px-5 py-2 rounded-lg text-[13px] font-medium transition-colors"
              >
                Yes, proceed
              </button>
              <button
                onClick={() => setLiquidateStep("idle")}
                className="text-[13px] text-white/40 hover:text-white/70 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {liquidateStep === "typing" && (
            <div className="flex items-center gap-3">
              <div>
                <p className="text-[11px] text-[#f76e6e] mb-1">Type LIQUIDATE to confirm</p>
                <input
                  type="text"
                  value={liquidateConfirm}
                  onChange={(e) => setLiquidateConfirm(e.target.value)}
                  autoFocus
                  className="bg-white/[0.03] border border-[#f76e6e]/30 rounded-lg px-4 py-2 text-[13px] text-[#f5f5f5] placeholder-white/30 focus:outline-none focus:border-[#f76e6e]/50 w-40"
                  placeholder="LIQUIDATE"
                />
              </div>
              <button
                onClick={executeLiquidation}
                disabled={liquidateConfirm !== "LIQUIDATE"}
                className="bg-[#f76e6e]/20 hover:bg-[#f76e6e]/30 text-[#f76e6e] border border-[#f76e6e]/20 px-5 py-2 rounded-lg text-[13px] font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Confirm
              </button>
              <button
                onClick={() => { setLiquidateStep("idle"); setLiquidateConfirm(""); }}
                className="text-[13px] text-white/40 hover:text-white/70 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {liquidateStep === "executing" && (
            <p className="text-[13px] text-yellow-400 animate-pulse">Liquidating all positions...</p>
          )}
        </div>

        {liquidateStep === "done" && liquidateResult && (
          <p className={`mt-4 text-[13px] ${liquidateResult.startsWith("Error") ? "text-[#f76e6e]" : "text-[#3dd68c]"}`}>
            {liquidateResult}
          </p>
        )}
      </div>
    </div>
  );
}

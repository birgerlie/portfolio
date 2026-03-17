import { prisma } from "@/lib/prisma";
import { createSupabaseServer } from "@/lib/supabase-server";
import { Hero } from "@/components/hero";
import { NavChart } from "@/components/nav-chart";
import { PositionList } from "@/components/position-list";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();

  const heartbeat = await prisma.engineHeartbeat.findFirst({ where: { id: "singleton" } });
  const engineOnline = heartbeat
    ? (Date.now() - new Date(heartbeat.updatedAt).getTime()) < 5 * 60 * 1000
    : false;

  if (!engineOnline) {
    return (
      <div className="pt-14 min-h-screen flex flex-col items-center justify-center px-6">
        <div className="w-2.5 h-2.5 rounded-full bg-white/20 mb-6" />
        <h1 className="text-xl font-medium tracking-tight text-white/70 mb-2">Engine Offline</h1>
        <p className="text-white/40 text-[13px] max-w-md text-center">
          The fund engine is not running. Data will appear here once the server is started.
        </p>
      </div>
    );
  }

  const snapshot = await prisma.fundSnapshot.findFirst({ orderBy: { date: "desc" } });

  const member = user
    ? await prisma.member.findUnique({ where: { authId: user.id } })
    : null;

  const navHistory = await prisma.weeklyNav.findMany({
    orderBy: { date: "asc" },
    select: { date: true, nav: true, grossReturnPct: true },
  });

  const positions = await prisma.position.findMany({
    orderBy: { marketValue: "desc" },
  });

  const journal = await prisma.journal.findFirst({
    orderBy: { updatedAt: "desc" },
  });

  const narratives = await prisma.narrative.findMany({
    orderBy: { createdAt: "desc" },
    take: 20,
  });

  const currentValue = member && snapshot
    ? member.units * snapshot.navPerUnit
    : snapshot?.nav ?? 0;

  const returnPct = member && member.costBasis > 0
    ? ((currentValue - member.costBasis) / member.costBasis) * 100
    : 0;

  const fundNav = snapshot?.nav ?? 0;
  const cash = snapshot?.cash ?? 0;
  const cashPct = fundNav > 0 ? (cash / fundNav) * 100 : 0;
  const totalPl = positions.reduce((sum, p) => sum + p.unrealizedPl, 0);
  const weeklyReturn = navHistory.length > 0 ? navHistory[navHistory.length - 1].grossReturnPct : 0;

  return (
    <div className="pt-12">
      <Hero currentValue={currentValue} returnPct={returnPct} />

      <section className="max-w-5xl mx-auto px-6 -mt-32">
        <NavChart data={navHistory.map((n) => ({ date: n.date, nav: n.nav }))} />
      </section>

      {/* Key Numbers */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/[0.04] rounded-lg overflow-hidden">
          <Stat label="Fund NAV" value={`$${fundNav.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
          <Stat label="This Week" value={`${weeklyReturn >= 0 ? "+" : ""}${(weeklyReturn * 100).toFixed(2)}%`} positive={weeklyReturn >= 0} />
          <Stat label="Unrealized P&L" value={`${totalPl >= 0 ? "+" : ""}$${Math.abs(totalPl).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} positive={totalPl >= 0} />
          <Stat label="Cash" value={`${cashPct.toFixed(1)}%`} sublabel={`$${cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
        </div>
      </section>

      {journal && <EngineAnalysis journal={journal} regime={heartbeat?.currentRegime ?? ""} />}

      {narratives.length > 0 && <NarrativeFeed narratives={narratives} />}

      <PositionList
        positions={positions}
        totalValue={snapshot?.nav ?? 0}
        cash={snapshot?.cash ?? 0}
      />
    </div>
  );
}

function EngineAnalysis({ journal, regime }: { journal: { regimeSummary: string; entries: unknown; updatedAt: Date }; regime: string }) {
  const entries = journal.entries as Record<string, unknown> | null;
  if (!entries) return null;

  const strategy = entries.strategy as string ?? "";
  const overallConfidence = entries.overall_confidence as number ?? 0;
  const trades = (entries.trades as Array<{ type: string; symbol: string; allocation: number; reason: string }>) ?? [];
  const detectedRegime = (entries.regime as string) ?? regime;
  const silicondb = entries.silicondb as Record<string, unknown> | null;
  const contradictions = (silicondb?.contradictions as Array<{ a: string; b: string; score: number }>) ?? [];
  const uncertainBeliefs = (silicondb?.uncertain as Array<{ id: string; entropy: number }>) ?? [];
  const beliefEngine = (entries.belief_engine as string) ?? "local";

  const regimeColors: Record<string, string> = {
    bull: "text-[#3dd68c]",
    bear: "text-[#f76e6e]",
    transition: "text-yellow-400",
    consolidation: "text-blue-400",
  };

  const regimeLabels: Record<string, string> = {
    bull: "Bull Market",
    bear: "Bear Market",
    transition: "Transition",
    consolidation: "Consolidation",
  };

  return (
    <section className="max-w-5xl mx-auto px-6 pb-12">
      <div className="border border-white/[0.06] rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Engine Analysis</h2>
          <span className="text-[11px] text-white/30">
            Updated {new Date(journal.updatedAt).toLocaleTimeString()}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
          <div>
            <span className="text-[11px] text-white/40 uppercase tracking-[0.05em] font-medium">Market Regime</span>
            <p className={`text-lg font-medium tracking-tight ${regimeColors[detectedRegime] ?? "text-white/70"}`}>
              {regimeLabels[detectedRegime] ?? detectedRegime}
            </p>
          </div>
          <div>
            <span className="text-[11px] text-white/40 uppercase tracking-[0.05em] font-medium">Active Strategy</span>
            <p className="text-lg font-medium tracking-tight text-white/90">{strategy.replace(/_/g, " ")}</p>
          </div>
          <div>
            <span className="text-[11px] text-white/40 uppercase tracking-[0.05em] font-medium">Confidence</span>
            <p className="text-lg font-medium tracking-tight text-white/90">{(overallConfidence * 100).toFixed(0)}%</p>
          </div>
        </div>

        {trades.length > 0 && (
          <div className="mb-5">
            <span className="text-[11px] text-white/40 uppercase tracking-[0.05em] font-medium mb-2 block">Suggested Trades</span>
            <div className="space-y-1">
              {trades.map((t, i) => (
                <div key={i} className="flex items-center gap-3 text-[13px]">
                  <span className={`w-10 text-[11px] font-medium ${t.type === "BUY" ? "text-[#3dd68c]" : "text-[#f76e6e]"}`}>
                    {t.type}
                  </span>
                  <span className="text-white/90 font-medium w-12">{t.symbol}</span>
                  <span className="text-white/40 text-[11px] flex-1">{t.reason}</span>
                  <span className="text-white/65 text-[11px]">{(t.allocation * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {(contradictions.length > 0 || uncertainBeliefs.length > 0) && (
          <div className="border-t border-white/[0.06] pt-4 mt-2">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-[11px] text-white/40 uppercase tracking-[0.05em] font-medium">Epistemology</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-white/40">SiliconDB</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {contradictions.length > 0 && (
                <div>
                  <span className="text-[11px] text-[#f76e6e]/70 mb-1.5 block">Contradictions Detected</span>
                  {contradictions.map((c, i) => (
                    <div key={i} className="text-[11px] text-white/65 flex justify-between py-0.5">
                      <span>{c.a.replace("belief:", "").replace(":return", "")} vs {c.b.replace("belief:", "").replace(":return", "")}</span>
                      <span className="text-[#f76e6e]/60">{(c.score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              )}
              {uncertainBeliefs.length > 0 && (
                <div>
                  <span className="text-[11px] text-yellow-400/70 mb-1.5 block">High Uncertainty (needs data)</span>
                  {uncertainBeliefs.map((u, i) => (
                    <div key={i} className="text-[11px] text-white/65 flex justify-between py-0.5">
                      <span>{u.id.replace("belief:", "").replace(":return", "")}</span>
                      <span className="text-yellow-400/60">entropy {u.entropy.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mt-4 pt-3 border-t border-white/[0.03] flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${beliefEngine === "silicondb" ? "bg-blue-400" : "bg-white/20"}`} />
          <span className="text-[10px] text-white/30">
            {beliefEngine === "silicondb" ? "Beliefs powered by SiliconDB epistemology" : "Local belief classification"}
          </span>
        </div>
      </div>
    </section>
  );
}

function NarrativeFeed({ narratives }: { narratives: { id: string; kind: string; symbol: string; content: string; createdAt: Date }[] }) {
  const kindIcons: Record<string, string> = {
    thermo: "\u{1F321}",
    contradiction: "\u{26A0}",
    briefing: "\u{1F4CB}",
    trade: "\u{1F4B9}",
    regime: "\u{1F310}",
  };
  const kindColors: Record<string, string> = {
    thermo: "text-purple-400",
    contradiction: "text-[#f76e6e]",
    briefing: "text-blue-400",
    trade: "text-[#3dd68c]",
    regime: "text-yellow-400",
  };

  return (
    <section className="max-w-5xl mx-auto px-6 pb-12">
      <div className="border border-white/[0.06] rounded-lg overflow-hidden">
        <div className="px-5 py-3 border-b border-white/[0.06]">
          <h2 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Market Intelligence</h2>
        </div>
        <div className="divide-y divide-white/[0.03]">
          {narratives.map((n) => (
            <div key={n.id} className="px-5 py-3 hover:bg-white/[0.02] transition-colors">
              <div className="flex items-start gap-3">
                <span className="text-[13px] mt-0.5">{kindIcons[n.kind] || "\u{2022}"}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-[11px] font-medium uppercase tracking-[0.05em] ${kindColors[n.kind] || "text-white/40"}`}>
                      {n.kind}
                    </span>
                    {n.symbol && (
                      <span className="text-[11px] text-white/65 font-medium">{n.symbol}</span>
                    )}
                    <span className="text-[10px] text-white/25 ml-auto">
                      {new Date(n.createdAt).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-[13px] text-white/65 leading-relaxed">{n.content}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value, sublabel, positive }: { label: string; value: string; sublabel?: string; positive?: boolean }) {
  const color = positive === undefined ? "text-[#f5f5f5]" : positive ? "text-[#3dd68c]" : "text-[#f76e6e]";
  return (
    <div className="bg-[#0a0a0a] p-4">
      <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">{label}</span>
      <p className={`text-xl font-medium tracking-tight mt-1.5 ${color}`}>{value}</p>
      {sublabel && <p className="text-[11px] text-white/30 mt-0.5">{sublabel}</p>}
    </div>
  );
}

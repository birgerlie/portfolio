import { prisma } from "@/lib/prisma";
import { createSupabaseServer } from "@/lib/supabase-server";
import { Hero } from "@/components/hero";
import { NavChart } from "@/components/nav-chart";
import { PositionList } from "@/components/position-list";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();

  // Check if engine is online (heartbeat updated within last 5 minutes)
  const heartbeat = await prisma.engineHeartbeat.findFirst({ where: { id: "singleton" } });
  const engineOnline = heartbeat
    ? (Date.now() - new Date(heartbeat.updatedAt).getTime()) < 5 * 60 * 1000
    : false;

  if (!engineOnline) {
    return (
      <div className="pt-14 min-h-screen flex flex-col items-center justify-center px-6">
        <div className="w-3 h-3 rounded-full bg-zinc-700 mb-6" />
        <h1 className="text-2xl font-light text-zinc-300 mb-2">Engine Offline</h1>
        <p className="text-zinc-600 text-sm max-w-md text-center">
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

  const currentValue = member && snapshot
    ? member.units * snapshot.navPerUnit
    : snapshot?.nav ?? 0;

  const returnPct = member && member.costBasis > 0
    ? ((currentValue - member.costBasis) / member.costBasis) * 100
    : 0;

  // Fund-level stats
  const fundNav = snapshot?.nav ?? 0;
  const cash = snapshot?.cash ?? 0;
  const cashPct = fundNav > 0 ? (cash / fundNav) * 100 : 0;
  const totalPl = positions.reduce((sum, p) => sum + p.unrealizedPl, 0);
  const weeklyReturn = navHistory.length > 0 ? navHistory[navHistory.length - 1].grossReturnPct : 0;

  return (
    <div className="pt-14">
      <Hero currentValue={currentValue} returnPct={returnPct} />

      {/* NAV Chart */}
      <section className="max-w-5xl mx-auto px-6 -mt-32">
        <NavChart data={navHistory.map((n) => ({ date: n.date, nav: n.nav }))} />
      </section>

      {/* Key Numbers */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Fund NAV" value={`$${fundNav.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
          <Stat label="This Week" value={`${weeklyReturn >= 0 ? "+" : ""}${(weeklyReturn * 100).toFixed(2)}%`} positive={weeklyReturn >= 0} />
          <Stat label="Unrealized P&L" value={`${totalPl >= 0 ? "+" : ""}$${Math.abs(totalPl).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} positive={totalPl >= 0} />
          <Stat label="Cash" value={`${cashPct.toFixed(1)}%`} sublabel={`$${cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
        </div>
      </section>

      {/* Engine Analysis */}
      {journal && <EngineAnalysis journal={journal} regime={heartbeat?.currentRegime ?? ""} />}

      {/* Positions */}
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
  const strategyConfidence = entries.strategy_confidence as number ?? 0;
  const overallConfidence = entries.overall_confidence as number ?? 0;
  const trades = (entries.trades as Array<{ type: string; symbol: string; allocation: number; reason: string }>) ?? [];
  const detectedRegime = (entries.regime as string) ?? regime;
  const silicondb = entries.silicondb as Record<string, unknown> | null;
  const contradictions = (silicondb?.contradictions as Array<{ a: string; b: string; score: number }>) ?? [];
  const uncertainBeliefs = (silicondb?.uncertain as Array<{ id: string; entropy: number }>) ?? [];
  const beliefEngine = (entries.belief_engine as string) ?? "local";

  const regimeColors: Record<string, string> = {
    bull: "text-green-400",
    bear: "text-red-400",
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
      <div className="bg-zinc-900/50 rounded-2xl border border-zinc-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm uppercase tracking-wider text-zinc-500">Engine Analysis</h2>
          <span className="text-xs text-zinc-600">
            Updated {new Date(journal.updatedAt).toLocaleTimeString()}
          </span>
        </div>

        {/* Regime & Strategy */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div>
            <span className="text-xs text-zinc-500">Market Regime</span>
            <p className={`text-lg font-medium ${regimeColors[detectedRegime] ?? "text-zinc-300"}`}>
              {regimeLabels[detectedRegime] ?? detectedRegime}
            </p>
          </div>
          <div>
            <span className="text-xs text-zinc-500">Active Strategy</span>
            <p className="text-lg font-medium text-zinc-200">{strategy.replace(/_/g, " ")}</p>
          </div>
          <div>
            <span className="text-xs text-zinc-500">Confidence</span>
            <p className="text-lg font-medium text-zinc-200">{(overallConfidence * 100).toFixed(0)}%</p>
          </div>
        </div>

        {/* Trade Suggestions */}
        {trades.length > 0 && (
          <div className="mb-6">
            <span className="text-xs text-zinc-500 mb-2 block">Suggested Trades</span>
            <div className="space-y-1.5">
              {trades.map((t, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span className={`w-10 text-xs font-medium ${t.type === "BUY" ? "text-green-400" : "text-red-400"}`}>
                    {t.type}
                  </span>
                  <span className="text-zinc-200 font-medium w-12">{t.symbol}</span>
                  <span className="text-zinc-500 text-xs flex-1">{t.reason}</span>
                  <span className="text-zinc-400 text-xs">{(t.allocation * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SiliconDB Epistemology Insights */}
        {(contradictions.length > 0 || uncertainBeliefs.length > 0) && (
          <div className="border-t border-zinc-800 pt-4 mt-2">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Epistemology</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">SiliconDB</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {contradictions.length > 0 && (
                <div>
                  <span className="text-xs text-red-400/70 mb-1.5 block">Contradictions Detected</span>
                  {contradictions.map((c, i) => (
                    <div key={i} className="text-xs text-zinc-400 flex justify-between py-0.5">
                      <span>{c.a.replace("belief:", "").replace(":return", "")} vs {c.b.replace("belief:", "").replace(":return", "")}</span>
                      <span className="text-red-400/60">{(c.score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              )}
              {uncertainBeliefs.length > 0 && (
                <div>
                  <span className="text-xs text-yellow-400/70 mb-1.5 block">High Uncertainty (needs data)</span>
                  {uncertainBeliefs.map((u, i) => (
                    <div key={i} className="text-xs text-zinc-400 flex justify-between py-0.5">
                      <span>{u.id.replace("belief:", "").replace(":return", "")}</span>
                      <span className="text-yellow-400/60">entropy {u.entropy.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Belief engine indicator */}
        <div className="mt-4 pt-3 border-t border-zinc-800/50 flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${beliefEngine === "silicondb" ? "bg-blue-400" : "bg-zinc-600"}`} />
          <span className="text-[10px] text-zinc-600">
            {beliefEngine === "silicondb" ? "Beliefs powered by SiliconDB epistemology" : "Local belief classification"}
          </span>
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value, sublabel, positive }: { label: string; value: string; sublabel?: string; positive?: boolean }) {
  const color = positive === undefined ? "text-white" : positive ? "text-green-400" : "text-red-400";
  return (
    <div className="bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
      <span className="text-xs text-zinc-500 uppercase tracking-wider">{label}</span>
      <p className={`text-2xl font-light mt-1 ${color}`}>{value}</p>
      {sublabel && <p className="text-xs text-zinc-600 mt-0.5">{sublabel}</p>}
    </div>
  );
}

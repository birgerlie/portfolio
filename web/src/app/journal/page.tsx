import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function JournalPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const params = await searchParams;
  const date = params.date ?? new Date().toISOString().split("T")[0];

  const journal = await prisma.journal.findUnique({ where: { date } });

  const dates = await prisma.journal.findMany({
    select: { date: true },
    orderBy: { date: "desc" },
    take: 30,
  });

  const entries = journal?.entries as Record<string, unknown> | null;
  const trades = (entries?.trades as Array<{ type: string; symbol: string; allocation: number; reason: string }>) ?? [];
  const regime = (entries?.regime as string) ?? "";
  const strategy = (entries?.strategy as string) ?? "";
  const confidence = (entries?.overall_confidence as number) ?? 0;
  const silicondb = entries?.silicondb as Record<string, unknown> | null;
  const briefing = silicondb?.briefing as Record<string, unknown> | null;
  const thermo = silicondb?.thermo as Record<string, unknown> | null;
  const contradictions = (silicondb?.contradictions as Array<{ a: string; b: string; score: number }>) ?? [];
  const percolator = (silicondb?.percolator as Array<{ type: string; summary: string }>) ?? [];

  const regimeColors: Record<string, string> = {
    bull: "text-green-400",
    bear: "text-red-400",
    transition: "text-yellow-400",
    consolidation: "text-blue-400",
  };

  return (
    <div className="min-h-screen pt-28 px-6 max-w-3xl mx-auto">
      <h1 className="text-4xl font-light mb-2">Journal</h1>
      <p className="text-zinc-500 mb-8">Engine analysis and belief state, day by day</p>

      <div className="flex gap-2 mb-8 overflow-x-auto pb-2">
        {dates.map((d) => (
          <a key={d.date} href={`/journal?date=${d.date}`}
            className={`px-3 py-1 rounded-full text-xs whitespace-nowrap transition-colors ${
              d.date === date ? "bg-white text-black" : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800"
            }`}>
            {d.date}
          </a>
        ))}
      </div>

      {journal ? (
        <div className="space-y-8">
          {/* Header stats */}
          <div className="flex gap-8 text-sm">
            <div>
              <span className="text-zinc-500">Regime</span>
              <p className={`text-xl font-light ${regimeColors[regime] ?? "text-zinc-300"}`}>
                {regime || "—"}
              </p>
            </div>
            <div>
              <span className="text-zinc-500">Strategy</span>
              <p className="text-xl font-light text-zinc-200">{(strategy || "—").replace(/_/g, " ")}</p>
            </div>
            <div>
              <span className="text-zinc-500">Confidence</span>
              <p className="text-xl font-light text-zinc-200">{(confidence * 100).toFixed(0)}%</p>
            </div>
            <div>
              <span className="text-zinc-500">Trades</span>
              <p className="text-xl font-light">{journal.tradesExecuted}</p>
            </div>
          </div>

          {/* Regime summary / narrative */}
          {journal.regimeSummary && (
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-4">
              <p className="text-sm text-zinc-300 leading-relaxed">{journal.regimeSummary}</p>
            </div>
          )}

          {/* Thermodynamic state */}
          {thermo && (
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-4">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Thermodynamic State</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <span className="text-zinc-500">Temperature</span>
                  <p className="text-zinc-200">{(thermo.temperature as number)?.toFixed(2)}</p>
                </div>
                <div>
                  <span className="text-zinc-500">Entropy</span>
                  <p className="text-zinc-200">{(thermo.entropy_production as number)?.toFixed(2)}</p>
                </div>
                <div>
                  <span className="text-zinc-500">Criticality</span>
                  <p className="text-zinc-200">{(thermo.criticality as number)?.toFixed(2)}</p>
                </div>
                <div>
                  <span className="text-zinc-500">Tier</span>
                  <p className="text-zinc-200">{thermo.criticality_tier as string}</p>
                </div>
              </div>
            </div>
          )}

          {/* Epistemic briefing */}
          {briefing && (
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-4">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Epistemic Briefing</h3>
              <div className="grid grid-cols-5 gap-3 text-sm mb-4">
                <div className="text-center">
                  <p className="text-lg font-light text-zinc-200">{briefing.anchors as number}</p>
                  <span className="text-[10px] text-zinc-500">Anchors</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-light text-yellow-400">{briefing.surprises as number}</p>
                  <span className="text-[10px] text-zinc-500">Surprises</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-light text-red-400">{briefing.conflicts as number}</p>
                  <span className="text-[10px] text-zinc-500">Conflicts</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-light text-orange-400">{briefing.gaps as number}</p>
                  <span className="text-[10px] text-zinc-500">Gaps</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-light text-cyan-400">{briefing.time_sensitive as number}</p>
                  <span className="text-[10px] text-zinc-500">Time-sensitive</span>
                </div>
              </div>
            </div>
          )}

          {/* Trade suggestions */}
          {trades.length > 0 && (
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-4">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Trade Suggestions</h3>
              <div className="space-y-2">
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

          {/* Contradictions */}
          {contradictions.length > 0 && (
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-4">
              <h3 className="text-xs text-red-400/70 uppercase tracking-wider mb-3">Contradictions</h3>
              {contradictions.map((c, i) => (
                <div key={i} className="text-sm text-zinc-400 flex justify-between py-1">
                  <span>{c.a} vs {c.b}</span>
                  <span className="text-red-400/60">{(c.score * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Percolator events */}
          {percolator.length > 0 && (
            <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-4">
              <h3 className="text-xs text-cyan-400/70 uppercase tracking-wider mb-3">Percolator Events</h3>
              {percolator.map((p, i) => (
                <div key={i} className="text-sm text-zinc-400 py-1">
                  <span className="text-zinc-500 text-xs">[{p.type}]</span> {p.summary}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <p className="text-zinc-600">No journal data for {date}</p>
      )}
    </div>
  );
}

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
    bull: "text-[#3dd68c]",
    bear: "text-[#f76e6e]",
    transition: "text-yellow-400",
    consolidation: "text-blue-400",
  };

  return (
    <div className="min-h-screen pt-24 px-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-medium tracking-tight mb-1">Journal</h1>
      <p className="text-white/40 text-[13px] mb-8">Engine analysis and belief state, day by day</p>

      <div className="flex gap-1.5 mb-8 overflow-x-auto pb-2">
        {dates.map((d) => (
          <a key={d.date} href={`/journal?date=${d.date}`}
            className={`px-3 py-1 rounded-md text-[11px] whitespace-nowrap transition-colors ${
              d.date === date ? "bg-white text-[#0a0a0a] font-medium" : "bg-white/[0.06] text-white/45 hover:bg-white/[0.1]"
            }`}>
            {d.date}
          </a>
        ))}
      </div>

      {journal ? (
        <div className="space-y-6">
          {/* Header stats */}
          <div className="flex gap-8 text-[13px]">
            <div>
              <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Regime</span>
              <p className={`text-lg font-medium tracking-tight ${regimeColors[regime] ?? "text-white/70"}`}>
                {regime || "—"}
              </p>
            </div>
            <div>
              <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Strategy</span>
              <p className="text-lg font-medium tracking-tight text-white/90">{(strategy || "—").replace(/_/g, " ")}</p>
            </div>
            <div>
              <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Confidence</span>
              <p className="text-lg font-medium tracking-tight text-white/90">{(confidence * 100).toFixed(0)}%</p>
            </div>
            <div>
              <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Trades</span>
              <p className="text-lg font-medium tracking-tight text-[#f5f5f5]">{journal.tradesExecuted}</p>
            </div>
          </div>

          {journal.regimeSummary && (
            <div className="border border-white/[0.06] rounded-lg p-4">
              <p className="text-[13px] text-white/70 leading-relaxed">{journal.regimeSummary}</p>
            </div>
          )}

          {thermo && (
            <div className="border border-white/[0.06] rounded-lg p-4">
              <h3 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-3">Thermodynamic State</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-[13px]">
                <div>
                  <span className="text-[11px] text-white/40">Temperature</span>
                  <p className="text-white/90">{(thermo.temperature as number)?.toFixed(2)}</p>
                </div>
                <div>
                  <span className="text-[11px] text-white/40">Entropy</span>
                  <p className="text-white/90">{(thermo.entropy_production as number)?.toFixed(2)}</p>
                </div>
                <div>
                  <span className="text-[11px] text-white/40">Criticality</span>
                  <p className="text-white/90">{(thermo.criticality as number)?.toFixed(2)}</p>
                </div>
                <div>
                  <span className="text-[11px] text-white/40">Tier</span>
                  <p className="text-white/90">{thermo.criticality_tier as string}</p>
                </div>
              </div>
            </div>
          )}

          {briefing && (
            <div className="border border-white/[0.06] rounded-lg p-4">
              <h3 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-3">Epistemic Briefing</h3>
              <div className="grid grid-cols-5 gap-3 text-[13px] mb-4">
                <div className="text-center">
                  <p className="text-lg font-medium tracking-tight text-white/90">{briefing.anchors as number}</p>
                  <span className="text-[10px] text-white/40">Anchors</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-medium tracking-tight text-yellow-400">{briefing.surprises as number}</p>
                  <span className="text-[10px] text-white/40">Surprises</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-medium tracking-tight text-[#f76e6e]">{briefing.conflicts as number}</p>
                  <span className="text-[10px] text-white/40">Conflicts</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-medium tracking-tight text-orange-400">{briefing.gaps as number}</p>
                  <span className="text-[10px] text-white/40">Gaps</span>
                </div>
                <div className="text-center">
                  <p className="text-lg font-medium tracking-tight text-cyan-400">{briefing.time_sensitive as number}</p>
                  <span className="text-[10px] text-white/40">Time-sensitive</span>
                </div>
              </div>
            </div>
          )}

          {trades.length > 0 && (
            <div className="border border-white/[0.06] rounded-lg p-4">
              <h3 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-3">Trade Suggestions</h3>
              <div className="space-y-1.5">
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

          {contradictions.length > 0 && (
            <div className="border border-white/[0.06] rounded-lg p-4">
              <h3 className="text-[11px] uppercase tracking-[0.05em] text-[#f76e6e]/70 font-medium mb-3">Contradictions</h3>
              {contradictions.map((c, i) => (
                <div key={i} className="text-[13px] text-white/65 flex justify-between py-1">
                  <span>{c.a} vs {c.b}</span>
                  <span className="text-[#f76e6e]/60">{(c.score * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {percolator.length > 0 && (
            <div className="border border-white/[0.06] rounded-lg p-4">
              <h3 className="text-[11px] uppercase tracking-[0.05em] text-cyan-400/70 font-medium mb-3">Percolator Events</h3>
              {percolator.map((p, i) => (
                <div key={i} className="text-[13px] text-white/65 py-1">
                  <span className="text-white/40 text-[11px]">[{p.type}]</span> {p.summary}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <p className="text-white/30 text-[13px]">No journal data for {date}</p>
      )}
    </div>
  );
}

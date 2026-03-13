import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const weeks = await prisma.weeklyNav.findMany({
    orderBy: { date: "desc" },
    take: 52,
  });

  const snapshot = await prisma.fundSnapshot.findFirst({
    orderBy: { date: "desc" },
  });

  const positions = await prisma.position.findMany({
    orderBy: { marketValue: "desc" },
  });

  const totalReturn = weeks.length > 1
    ? ((weeks[0].nav - weeks[weeks.length - 1].nav) / weeks[weeks.length - 1].nav) * 100
    : 0;

  return (
    <div className="min-h-screen pt-24 px-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-medium tracking-tight mb-1">Reports</h1>
      <p className="text-white/40 text-[13px] mb-8">Weekly performance and fund metrics</p>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/[0.04] rounded-lg overflow-hidden mb-12">
        <div className="bg-[#0a0a0a] p-4">
          <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Fund NAV</span>
          <p className="text-xl font-medium tracking-tight mt-1.5">${snapshot?.nav?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}</p>
        </div>
        <div className="bg-[#0a0a0a] p-4">
          <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">NAV/Unit</span>
          <p className="text-xl font-medium tracking-tight mt-1.5">${snapshot?.navPerUnit?.toFixed(4) ?? "—"}</p>
        </div>
        <div className="bg-[#0a0a0a] p-4">
          <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Cash</span>
          <p className="text-xl font-medium tracking-tight mt-1.5">${snapshot?.cash?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}</p>
        </div>
        <div className="bg-[#0a0a0a] p-4">
          <span className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Total Return</span>
          <p className={`text-xl font-medium tracking-tight mt-1.5 ${totalReturn >= 0 ? "text-[#3dd68c]" : "text-[#f76e6e]"}`}>
            {totalReturn >= 0 ? "+" : ""}{totalReturn.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Positions */}
      <h2 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-4">Positions</h2>
      <div className="mb-12">
        {positions.length > 0 ? (
          <div className="border border-white/[0.06] rounded-lg overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="text-left py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Symbol</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Qty</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Price</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Value</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">P&L</th>
                  <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Alloc</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="py-2.5 px-4 font-medium text-[#f5f5f5]">{p.symbol}</td>
                    <td className="text-right py-2.5 px-4 text-white/65">{p.quantity.toFixed(1)}</td>
                    <td className="text-right py-2.5 px-4 text-white/65">${p.currentPrice.toFixed(2)}</td>
                    <td className="text-right py-2.5 px-4 text-white/65">${p.marketValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td className={`text-right py-2.5 px-4 ${p.unrealizedPl >= 0 ? "text-[#3dd68c]" : "text-[#f76e6e]"}`}>
                      {p.unrealizedPl >= 0 ? "+" : ""}{p.unrealizedPlPct.toFixed(1)}%
                    </td>
                    <td className="text-right py-2.5 px-4 text-white/65">{p.allocationPct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-white/30 text-[13px]">No positions</p>
        )}
      </div>

      {/* Weekly NAV History */}
      <h2 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-4">Weekly NAV</h2>
      <div className="border border-white/[0.06] rounded-lg overflow-hidden">
        {weeks.map((w, i) => (
          <div key={w.date} className={`flex items-center justify-between py-2.5 px-4 text-[13px] ${i < weeks.length - 1 ? "border-b border-white/[0.03]" : ""} hover:bg-white/[0.02] transition-colors`}>
            <span className="text-white/40 w-28">{w.date}</span>
            <span className="text-white/65">${w.nav.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span className={`w-20 text-right ${w.grossReturnPct >= 0 ? "text-[#3dd68c]" : "text-[#f76e6e]"}`}>
              {w.grossReturnPct >= 0 ? "+" : ""}{(w.grossReturnPct * 100).toFixed(2)}%
            </span>
            <span className="text-white/40 w-20 text-right">{w.marketHealth}</span>
          </div>
        ))}
        {weeks.length === 0 && <p className="text-white/30 text-[13px] p-4">No weekly data yet</p>}
      </div>
    </div>
  );
}

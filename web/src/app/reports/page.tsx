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
    <div className="min-h-screen pt-28 px-6 max-w-4xl mx-auto">
      <h1 className="text-4xl font-light mb-2">Reports</h1>
      <p className="text-zinc-500 mb-8">Weekly performance and fund metrics</p>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
        <div className="bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
          <span className="text-sm text-zinc-500">Fund NAV</span>
          <p className="text-2xl font-light">${snapshot?.nav?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}</p>
        </div>
        <div className="bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
          <span className="text-sm text-zinc-500">NAV/Unit</span>
          <p className="text-2xl font-light">${snapshot?.navPerUnit?.toFixed(4) ?? "—"}</p>
        </div>
        <div className="bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
          <span className="text-sm text-zinc-500">Cash</span>
          <p className="text-2xl font-light">${snapshot?.cash?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}</p>
        </div>
        <div className="bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
          <span className="text-sm text-zinc-500">Total Return</span>
          <p className={`text-2xl font-light ${totalReturn >= 0 ? "text-green-400" : "text-red-400"}`}>
            {totalReturn >= 0 ? "+" : ""}{totalReturn.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Positions */}
      <h2 className="text-2xl font-light mb-4">Positions</h2>
      <div className="mb-12">
        {positions.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-3 font-normal">Symbol</th>
                <th className="text-right py-3 font-normal">Qty</th>
                <th className="text-right py-3 font-normal">Price</th>
                <th className="text-right py-3 font-normal">Value</th>
                <th className="text-right py-3 font-normal">P&L</th>
                <th className="text-right py-3 font-normal">Alloc</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.symbol} className="border-b border-zinc-800/50">
                  <td className="py-3 font-medium">{p.symbol}</td>
                  <td className="text-right py-3 text-zinc-400">{p.quantity.toFixed(1)}</td>
                  <td className="text-right py-3 text-zinc-400">${p.currentPrice.toFixed(2)}</td>
                  <td className="text-right py-3">${p.marketValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                  <td className={`text-right py-3 ${p.unrealizedPl >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {p.unrealizedPl >= 0 ? "+" : ""}{p.unrealizedPlPct.toFixed(1)}%
                  </td>
                  <td className="text-right py-3 text-zinc-400">{p.allocationPct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-zinc-600">No positions</p>
        )}
      </div>

      {/* Weekly NAV History */}
      <h2 className="text-2xl font-light mb-4">Weekly NAV</h2>
      <div className="space-y-1">
        {weeks.map((w) => (
          <div key={w.date} className="flex items-center justify-between py-2 border-b border-zinc-800/30 text-sm">
            <span className="text-zinc-400 w-28">{w.date}</span>
            <span className="text-zinc-300">${w.nav.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span className={`w-20 text-right ${w.grossReturnPct >= 0 ? "text-green-400" : "text-red-400"}`}>
              {w.grossReturnPct >= 0 ? "+" : ""}{(w.grossReturnPct * 100).toFixed(2)}%
            </span>
            <span className="text-zinc-500 w-20 text-right">{w.marketHealth}</span>
          </div>
        ))}
        {weeks.length === 0 && <p className="text-zinc-600">No weekly data yet</p>}
      </div>
    </div>
  );
}

interface PositionRow {
  symbol: string; quantity: number; marketValue: number; currentPrice: number;
  unrealizedPl: number; unrealizedPlPct: number; allocationPct: number;
}
interface PositionListProps { positions: PositionRow[]; totalValue: number; cash: number; }

export function PositionList({ positions, totalValue, cash }: PositionListProps) {
  return (
    <section className="py-16 max-w-5xl mx-auto px-6">
      <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-8">The Engine Room</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-3 font-normal">Symbol</th>
              <th className="text-right py-3 font-normal">Qty</th>
              <th className="text-right py-3 font-normal">Price</th>
              <th className="text-right py-3 font-normal">Value</th>
              <th className="text-right py-3 font-normal">P&L</th>
              <th className="text-right py-3 font-normal">Weight</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.symbol} className="border-b border-zinc-900 hover:bg-zinc-900/50 transition-colors">
                <td className="py-3 font-medium">{p.symbol}</td>
                <td className="py-3 text-right text-zinc-400">{p.quantity}</td>
                <td className="py-3 text-right text-zinc-400">${p.currentPrice.toFixed(2)}</td>
                <td className="py-3 text-right">${p.marketValue.toLocaleString()}</td>
                <td className={`py-3 text-right ${p.unrealizedPl >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {p.unrealizedPl >= 0 ? "+" : ""}{p.unrealizedPlPct.toFixed(1)}%
                </td>
                <td className="py-3 text-right text-zinc-400">{(p.allocationPct * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="text-zinc-400">
              <td className="py-3">Cash</td><td colSpan={3}></td>
              <td className="py-3 text-right">${cash.toLocaleString()}</td><td></td>
            </tr>
            <tr className="font-medium border-t border-zinc-700">
              <td className="py-3">Total</td><td colSpan={3}></td>
              <td className="py-3 text-right">${totalValue.toLocaleString()}</td><td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

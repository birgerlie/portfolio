interface PositionRow {
  symbol: string; quantity: number; marketValue: number; currentPrice: number;
  unrealizedPl: number; unrealizedPlPct: number; allocationPct: number;
}
interface PositionListProps { positions: PositionRow[]; totalValue: number; cash: number; }

export function PositionList({ positions, totalValue, cash }: PositionListProps) {
  return (
    <section className="py-16 max-w-5xl mx-auto px-6">
      <h2 className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium mb-6">The Engine Room</h2>
      <div className="border border-white/[0.06] rounded-lg overflow-hidden">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-white/[0.06]">
              <th className="text-left py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Symbol</th>
              <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Qty</th>
              <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Price</th>
              <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Value</th>
              <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">P&L</th>
              <th className="text-right py-2.5 px-4 text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Weight</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.symbol} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                <td className="py-2.5 px-4 font-medium text-[#f5f5f5]">{p.symbol}</td>
                <td className="py-2.5 px-4 text-right text-white/65">{p.quantity}</td>
                <td className="py-2.5 px-4 text-right text-white/65">${p.currentPrice.toFixed(2)}</td>
                <td className="py-2.5 px-4 text-right text-white/65">${p.marketValue.toLocaleString()}</td>
                <td className={`py-2.5 px-4 text-right ${p.unrealizedPl >= 0 ? "text-[#3dd68c]" : "text-[#f76e6e]"}`}>
                  {p.unrealizedPl >= 0 ? "+" : ""}{p.unrealizedPlPct.toFixed(1)}%
                </td>
                <td className="py-2.5 px-4 text-right text-white/65">{(p.allocationPct * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="text-white/40">
              <td className="py-2.5 px-4">Cash</td><td colSpan={3}></td>
              <td className="py-2.5 px-4 text-right">${cash.toLocaleString()}</td><td></td>
            </tr>
            <tr className="font-medium border-t border-white/[0.06]">
              <td className="py-2.5 px-4">Total</td><td colSpan={3}></td>
              <td className="py-2.5 px-4 text-right">${totalValue.toLocaleString()}</td><td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

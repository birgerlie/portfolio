import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function UniversePage() {
  const instruments = await prisma.instrument.findMany({ orderBy: { votesFor: "desc" } });

  return (
    <div className="min-h-screen pt-24 px-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-medium tracking-tight mb-1">Investment Universe</h1>
      <p className="text-white/40 text-[13px] mb-8">Max 20 instruments. Monthly voting determines what stays.</p>

      <div className="border border-white/[0.06] rounded-lg overflow-hidden">
        {instruments.map((inst, i) => (
          <div key={inst.symbol} className={`p-4 flex items-center justify-between ${i < instruments.length - 1 ? "border-b border-white/[0.03]" : ""} hover:bg-white/[0.02] transition-colors`}>
            <div>
              <div className="flex items-center gap-3">
                <span className="text-[13px] font-medium text-[#f5f5f5]">{inst.symbol}</span>
                <span className="text-[13px] text-white/65">{inst.name}</span>
                <span className="text-[11px] px-2 py-0.5 bg-white/[0.06] rounded-md text-white/40">{inst.assetClass}</span>
              </div>
              <p className="text-[13px] text-white/65 mt-1">{inst.thesis}</p>
              <p className="text-[11px] text-white/30 mt-1">Proposed by {inst.proposedBy} · {inst.votesFor} votes</p>
            </div>
            <form action="/api/universe/vote" method="POST">
              <input type="hidden" name="symbol" value={inst.symbol} />
              <button type="submit" className="px-4 py-2 bg-white/[0.06] hover:bg-white/[0.1] rounded-lg text-[13px] text-white/65 transition-colors">Vote</button>
            </form>
          </div>
        ))}
      </div>
    </div>
  );
}

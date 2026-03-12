import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function UniversePage() {
  const instruments = await prisma.instrument.findMany({ orderBy: { votesFor: "desc" } });

  return (
    <div className="min-h-screen pt-28 px-6 max-w-4xl mx-auto">
      <h1 className="text-4xl font-light mb-2">Investment Universe</h1>
      <p className="text-zinc-500 mb-8">Max 20 instruments. Monthly voting determines what stays.</p>

      <div className="grid gap-4">
        {instruments.map((inst) => (
          <div key={inst.symbol} className="bg-zinc-900/50 rounded-xl p-4 flex items-center justify-between border border-zinc-800">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-lg font-medium">{inst.symbol}</span>
                <span className="text-sm text-zinc-500">{inst.name}</span>
                <span className="text-xs px-2 py-0.5 bg-zinc-800 rounded-full text-zinc-400">{inst.assetClass}</span>
              </div>
              <p className="text-sm text-zinc-400 mt-1">{inst.thesis}</p>
              <p className="text-xs text-zinc-600 mt-1">Proposed by {inst.proposedBy} · {inst.votesFor} votes</p>
            </div>
            <form action="/api/universe/vote" method="POST">
              <input type="hidden" name="symbol" value={inst.symbol} />
              <button type="submit" className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm transition-colors">Vote</button>
            </form>
          </div>
        ))}
      </div>
    </div>
  );
}

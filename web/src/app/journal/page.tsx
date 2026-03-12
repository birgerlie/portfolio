import { prisma } from "@/lib/prisma";
import { Timeline } from "@/components/timeline";

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

  return (
    <div className="min-h-screen pt-28 px-6 max-w-3xl mx-auto">
      <h1 className="text-4xl font-light mb-2">Journal</h1>
      <p className="text-zinc-500 mb-8">Everything the engine did, day by day</p>

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
        <>
          <div className="flex gap-8 mb-8 text-sm">
            <div>
              <span className="text-zinc-500">Trades</span>
              <p className="text-xl font-light">{journal.tradesExecuted}</p>
            </div>
            <div>
              <span className="text-zinc-500">NAV Change</span>
              <p className={`text-xl font-light ${journal.navChangePct >= 0 ? "text-green-400" : "text-red-400"}`}>
                {journal.navChangePct >= 0 ? "+" : ""}{(journal.navChangePct * 100).toFixed(2)}%
              </p>
            </div>
            <div>
              <span className="text-zinc-500">Regime</span>
              <p className="text-xl font-light">{journal.regimeSummary || "—"}</p>
            </div>
          </div>
          <Timeline entries={journal.entries as { timestamp: string; type: string; summary: string }[]} />
        </>
      ) : (
        <p className="text-zinc-600">No journal data for {date}</p>
      )}
    </div>
  );
}

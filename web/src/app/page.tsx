import { prisma } from "@/lib/prisma";
import { createSupabaseServer } from "@/lib/supabase-server";
import { Hero } from "@/components/hero";
import { NavChart } from "@/components/nav-chart";
import { ActivityRings } from "@/components/activity-rings";
import { Narrative } from "@/components/narrative";
import { BenchmarkRace } from "@/components/benchmark-race";
import { PositionList } from "@/components/position-list";
import { Constellation } from "@/components/constellation";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();

  const snapshot = await prisma.fundSnapshot.findFirst({
    orderBy: { date: "desc" },
  });

  const member = user
    ? await prisma.member.findUnique({ where: { authId: user.id } })
    : null;

  const navHistory = await prisma.weeklyNav.findMany({
    orderBy: { date: "asc" },
    select: { date: true, nav: true },
  });

  const latestWeekly = await prisma.weeklyNav.findFirst({
    orderBy: { date: "desc" },
  });

  const positions = await prisma.position.findMany({
    orderBy: { marketValue: "desc" },
  });

  const currentValue = member && snapshot
    ? member.units * snapshot.navPerUnit
    : snapshot?.nav ?? 0;

  const returnPct = member && member.costBasis > 0
    ? ((currentValue - member.costBasis) / member.costBasis) * 100
    : 0;

  // Parse benchmarks JSON for the race
  const benchmarksRaw = latestWeekly?.benchmarks ?? {};
  const benchmarkEntries = typeof benchmarksRaw === "object" && benchmarksRaw !== null
    ? Object.entries(benchmarksRaw as Record<string, number>)
    : [];

  const raceEntries = [
    { name: "Fund", returnPct: latestWeekly?.grossReturnPct ?? 0, color: "#3b82f6" },
    ...benchmarkEntries.map(([name, value], i) => ({
      name,
      returnPct: typeof value === "number" ? value : 0,
      color: ["#a855f7", "#22c55e", "#f59e0b", "#ef4444"][i % 4],
    })),
  ];

  // Map positions to constellation stars (conviction/clarity as placeholder 0.5)
  const constellationStars = positions.map((p) => ({
    symbol: p.symbol,
    allocation: p.allocationPct,
    conviction: 0.5,
    clarity: 0.5,
  }));

  const narrativeText = latestWeekly?.narrativeSummary
    || "The market moves in cycles. We move with conviction.";

  return (
    <div className="pt-14">
      <Hero currentValue={currentValue} returnPct={returnPct} />
      <section className="max-w-5xl mx-auto px-6 -mt-32">
        <NavChart data={navHistory.map((n) => ({ date: n.date, nav: n.nav }))} />
      </section>
      <ActivityRings
        clarity={latestWeekly?.clarityScore ?? 0}
        opportunity={latestWeekly?.opportunityScore ?? 0}
        marketHealth={latestWeekly?.marketHealth ?? "green"}
      />
      <Narrative text={narrativeText} />
      <BenchmarkRace entries={raceEntries} />
      <Constellation stars={constellationStars} />
      <PositionList
        positions={positions}
        totalValue={snapshot?.nav ?? 0}
        cash={snapshot?.cash ?? 0}
      />
    </div>
  );
}

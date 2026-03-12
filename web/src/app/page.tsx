import { prisma } from "@/lib/prisma";
import { createSupabaseServer } from "@/lib/supabase-server";
import { Hero } from "@/components/hero";
import { NavChart } from "@/components/nav-chart";
import { PositionList } from "@/components/position-list";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();

  // Check if engine is online (heartbeat updated within last 5 minutes)
  const heartbeat = await prisma.engineHeartbeat.findFirst({ where: { id: "singleton" } });
  const engineOnline = heartbeat
    ? (Date.now() - new Date(heartbeat.updatedAt).getTime()) < 5 * 60 * 1000
    : false;

  if (!engineOnline) {
    return (
      <div className="pt-14 min-h-screen flex flex-col items-center justify-center px-6">
        <div className="w-3 h-3 rounded-full bg-zinc-700 mb-6" />
        <h1 className="text-2xl font-light text-zinc-300 mb-2">Engine Offline</h1>
        <p className="text-zinc-600 text-sm max-w-md text-center">
          The fund engine is not running. Data will appear here once the server is started.
        </p>
      </div>
    );
  }

  const snapshot = await prisma.fundSnapshot.findFirst({ orderBy: { date: "desc" } });

  const member = user
    ? await prisma.member.findUnique({ where: { authId: user.id } })
    : null;

  const navHistory = await prisma.weeklyNav.findMany({
    orderBy: { date: "asc" },
    select: { date: true, nav: true, grossReturnPct: true },
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

  // Fund-level stats
  const fundNav = snapshot?.nav ?? 0;
  const cash = snapshot?.cash ?? 0;
  const cashPct = fundNav > 0 ? (cash / fundNav) * 100 : 0;
  const totalPl = positions.reduce((sum, p) => sum + p.unrealizedPl, 0);
  const weeklyReturn = navHistory.length > 0 ? navHistory[navHistory.length - 1].grossReturnPct : 0;

  return (
    <div className="pt-14">
      <Hero currentValue={currentValue} returnPct={returnPct} />

      {/* NAV Chart */}
      <section className="max-w-5xl mx-auto px-6 -mt-32">
        <NavChart data={navHistory.map((n) => ({ date: n.date, nav: n.nav }))} />
      </section>

      {/* Key Numbers */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Fund NAV" value={`$${fundNav.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
          <Stat label="This Week" value={`${weeklyReturn >= 0 ? "+" : ""}${(weeklyReturn * 100).toFixed(2)}%`} positive={weeklyReturn >= 0} />
          <Stat label="Unrealized P&L" value={`${totalPl >= 0 ? "+" : ""}$${Math.abs(totalPl).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} positive={totalPl >= 0} />
          <Stat label="Cash" value={`${cashPct.toFixed(1)}%`} sublabel={`$${cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
        </div>
      </section>

      {/* Positions */}
      <PositionList
        positions={positions}
        totalValue={snapshot?.nav ?? 0}
        cash={snapshot?.cash ?? 0}
      />
    </div>
  );
}

function Stat({ label, value, sublabel, positive }: { label: string; value: string; sublabel?: string; positive?: boolean }) {
  const color = positive === undefined ? "text-white" : positive ? "text-green-400" : "text-red-400";
  return (
    <div className="bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
      <span className="text-xs text-zinc-500 uppercase tracking-wider">{label}</span>
      <p className={`text-2xl font-light mt-1 ${color}`}>{value}</p>
      {sublabel && <p className="text-xs text-zinc-600 mt-0.5">{sublabel}</p>}
    </div>
  );
}

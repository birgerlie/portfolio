import { prisma } from "@/lib/prisma";
import { createSupabaseServer } from "@/lib/supabase-server";
import { Hero } from "@/components/hero";
import { NavChart } from "@/components/nav-chart";

export const revalidate = 60;

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

  const currentValue = member && snapshot
    ? member.units * snapshot.navPerUnit
    : snapshot?.nav ?? 0;

  const returnPct = member && member.costBasis > 0
    ? ((currentValue - member.costBasis) / member.costBasis) * 100
    : 0;

  return (
    <div className="pt-14">
      <Hero currentValue={currentValue} returnPct={returnPct} />
      <section className="max-w-5xl mx-auto px-6 -mt-32">
        <NavChart data={navHistory.map((n) => ({ date: n.date, nav: n.nav }))} />
      </section>
    </div>
  );
}

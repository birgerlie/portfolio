import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/admin";

export const dynamic = "force-dynamic";

export async function GET() {
  const auth = await requireAdmin();
  if (auth.error) return NextResponse.json({ error: auth.error }, { status: auth.status });
  const [snapshot, members, txns, weeklyNavs] = await Promise.all([
    prisma.fundSnapshot.findFirst({ orderBy: { date: "desc" } }),
    prisma.member.findMany({ select: { units: true, costBasis: true } }),
    prisma.transaction.findMany({
      select: { type: true, amount: true, managementFee: true, performanceFee: true, status: true },
    }),
    prisma.weeklyNav.findMany({
      select: { mgmtFeeAccrued: true, perfFeeAccrued: true },
    }),
  ]);

  const completed = txns.filter((t) => t.status === "completed" || t.status === "settled");
  const subscriptions = completed.filter((t) => t.type === "subscribe");
  const redemptions = completed.filter((t) => t.type === "redeem");

  const totalInvested = subscriptions.reduce((s, t) => s + t.amount, 0);
  const totalRedeemed = redemptions.reduce((s, t) => s + t.amount, 0);
  const netInvested = totalInvested - totalRedeemed;

  const realizedMgmtFees = completed.reduce((s, t) => s + t.managementFee, 0);
  const realizedPerfFees = completed.reduce((s, t) => s + t.performanceFee, 0);
  const accruedMgmtFees = weeklyNavs.reduce((s, w) => s + w.mgmtFeeAccrued, 0);
  const accruedPerfFees = weeklyNavs.reduce((s, w) => s + w.perfFeeAccrued, 0);

  const totalUnits = members.reduce((s, m) => s + m.units, 0);
  const totalCostBasis = members.reduce((s, m) => s + m.costBasis, 0);

  return NextResponse.json({
    fund: {
      nav: snapshot?.nav ?? 0,
      navPerUnit: snapshot?.navPerUnit ?? 100,
      unitsOutstanding: snapshot?.unitsOutstanding ?? 0,
      cash: snapshot?.cash ?? 0,
      highWaterMark: snapshot?.highWaterMark ?? 0,
      positionsCount: snapshot?.positionsCount ?? 0,
      date: snapshot?.date ?? null,
    },
    capital: {
      totalInvested,
      totalRedeemed,
      netInvested,
      totalUnits,
      totalCostBasis,
      memberCount: members.length,
    },
    fees: {
      realizedMgmt: realizedMgmtFees,
      realizedPerf: realizedPerfFees,
      realizedTotal: realizedMgmtFees + realizedPerfFees,
      accruedMgmt: accruedMgmtFees,
      accruedPerf: accruedPerfFees,
      accruedTotal: accruedMgmtFees + accruedPerfFees,
      grandTotal: realizedMgmtFees + realizedPerfFees + accruedMgmtFees + accruedPerfFees,
    },
    transactions: {
      total: txns.length,
      completed: completed.length,
      pending: txns.filter((t) => t.status === "pending").length,
    },
  });
}

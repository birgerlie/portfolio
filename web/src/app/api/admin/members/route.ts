import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/admin";

export const dynamic = "force-dynamic";

export async function GET() {
  const auth = await requireAdmin();
  if (auth.error) return NextResponse.json({ error: auth.error }, { status: auth.status });

  const members = await prisma.member.findMany({
    orderBy: { joinDate: "desc" },
    include: {
      transactions: {
        select: { type: true, amount: true, units: true, status: true, createdAt: true },
        orderBy: { createdAt: "desc" },
      },
    },
  });

  const enriched = members.map((m) => {
    const completed = m.transactions.filter((t) => t.status === "completed" || t.status === "settled");
    const subscriptions = completed.filter((t) => t.type === "subscribe");
    const redemptions = completed.filter((t) => t.type === "redeem");
    const pendingRedemptions = m.transactions.filter((t) => t.type === "redeem" && t.status === "pending");

    return {
      id: m.id,
      name: m.name,
      email: m.email,
      role: m.role,
      units: m.units,
      costBasis: m.costBasis,
      joinDate: m.joinDate,
      totalInvested: subscriptions.reduce((s, t) => s + t.amount, 0),
      totalRedeemed: redemptions.reduce((s, t) => s + t.amount, 0),
      investmentCount: subscriptions.length,
      redemptionCount: redemptions.length,
      pendingRedemptions: pendingRedemptions.length,
      pendingRedemptionAmount: pendingRedemptions.reduce((s, t) => s + t.amount, 0),
      lastActivity: m.transactions[0]?.createdAt ?? null,
      _count: { transactions: m.transactions.length },
    };
  });

  return NextResponse.json(enriched);
}

export async function PATCH(req: Request) {
  const auth = await requireAdmin();
  if (auth.error) return NextResponse.json({ error: auth.error }, { status: auth.status });

  const { id, role } = await req.json();
  if (!id || !role) return NextResponse.json({ error: "id and role required" }, { status: 400 });
  if (!["admin", "member"].includes(role)) return NextResponse.json({ error: "Invalid role" }, { status: 400 });

  const member = await prisma.member.update({ where: { id }, data: { role } });
  return NextResponse.json(member);
}

export async function DELETE(req: Request) {
  const auth = await requireAdmin();
  if (auth.error) return NextResponse.json({ error: auth.error }, { status: auth.status });

  const { id } = await req.json();
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  await prisma.member.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}

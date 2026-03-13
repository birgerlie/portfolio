import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/admin";

export async function GET() {
  const members = await prisma.member.findMany({
    orderBy: { joinDate: "desc" },
    include: { _count: { select: { transactions: true } } },
  });

  return NextResponse.json(members);
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

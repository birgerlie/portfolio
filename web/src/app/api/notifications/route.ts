import { NextRequest, NextResponse } from "next/server";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

/**
 * GET /api/notifications
 * Returns recent notifications, newest first.
 * Query params:
 *   limit  — max rows (default 50)
 *   unread — if "true", only unread notifications
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const limit = Math.min(parseInt(searchParams.get("limit") ?? "50", 10), 200);
  const unreadOnly = searchParams.get("unread") === "true";

  const where = unreadOnly ? { read: false } : {};

  const notifications = await prisma.notification.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: limit,
  });

  return NextResponse.json({ notifications });
}

/**
 * POST /api/notifications/mark-read
 * Body: { ids: string[] }  — mark specific notifications as read.
 * Body: { all: true }      — mark all as read.
 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));

  if (body.all === true) {
    await prisma.notification.updateMany({ data: { read: true } });
    return NextResponse.json({ ok: true, updated: "all" });
  }

  const ids: string[] = Array.isArray(body.ids) ? body.ids : [];
  if (ids.length === 0) {
    return NextResponse.json({ error: "Provide ids[] or all:true" }, { status: 400 });
  }

  const result = await prisma.notification.updateMany({
    where: { id: { in: ids } },
    data: { read: true },
  });

  return NextResponse.json({ ok: true, updated: result.count });
}

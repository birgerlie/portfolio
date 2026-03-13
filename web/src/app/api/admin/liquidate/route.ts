import { NextResponse } from "next/server";

export async function POST() {
  const key = process.env.ALPACA_API_KEY;
  const secret = process.env.ALPACA_SECRET_KEY;
  const paper = process.env.ALPACA_PAPER !== "false";
  const baseUrl = paper
    ? "https://paper-api.alpaca.markets"
    : "https://api.alpaca.markets";

  if (!key || !secret) {
    return NextResponse.json({ error: "Alpaca credentials not configured" }, { status: 500 });
  }

  const headers = {
    "APCA-API-KEY-ID": key,
    "APCA-API-SECRET-KEY": secret,
  };

  // Cancel all open orders first
  await fetch(`${baseUrl}/v2/orders`, { method: "DELETE", headers });

  // Close all positions
  const res = await fetch(`${baseUrl}/v2/positions?cancel_orders=true`, {
    method: "DELETE",
    headers,
  });

  if (!res.ok) {
    const text = await res.text();
    return NextResponse.json({ error: `Alpaca error: ${text}` }, { status: res.status });
  }

  const closed = await res.json();

  // Clear positions in our DB
  const { prisma } = await import("@/lib/prisma");
  await prisma.position.deleteMany();

  return NextResponse.json({
    ok: true,
    closed: Array.isArray(closed) ? closed.length : 0,
    message: "All positions liquidated",
  });
}

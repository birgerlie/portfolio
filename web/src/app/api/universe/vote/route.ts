import { createSupabaseServer } from "@/lib/supabase-server";
import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { symbol } = await request.json();
  await prisma.instrument.update({
    where: { symbol },
    data: { votesFor: { increment: 1 } },
  });
  return NextResponse.json({ ok: true });
}

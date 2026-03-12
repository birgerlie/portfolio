import { stripe } from "@/lib/stripe";
import { createSupabaseServer } from "@/lib/supabase-server";
import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { amount } = await request.json();
  if (!amount || amount < 100) {
    return NextResponse.json({ error: "Minimum investment is €100" }, { status: 400 });
  }

  const member = await prisma.member.findUnique({ where: { authId: user.id } });
  if (!member) return NextResponse.json({ error: "Member not found" }, { status: 404 });

  const paymentIntent = await stripe.paymentIntents.create({
    amount: Math.round(amount * 100),
    currency: "eur",
    capture_method: "manual",
    metadata: { memberId: member.id, type: "subscription" },
  });

  return NextResponse.json({ clientSecret: paymentIntent.client_secret });
}

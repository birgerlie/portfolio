import { NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { prisma } from "@/lib/prisma";
import Stripe from "stripe";

export async function POST(request: Request) {
  const body = await request.text();
  const signature = request.headers.get("stripe-signature");

  if (!signature) {
    return NextResponse.json({ error: "Missing signature" }, { status: 400 });
  }

  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!webhookSecret) {
    return NextResponse.json({ error: "Webhook secret not configured" }, { status: 500 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, webhookSecret);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: `Webhook verification failed: ${message}` }, { status: 400 });
  }

  switch (event.type) {
    case "payment_intent.succeeded": {
      const pi = event.data.object as Stripe.PaymentIntent;
      const memberId = pi.metadata.memberId;
      if (!memberId) break;

      // Get current NAV per unit for unit allocation
      const snapshot = await prisma.fundSnapshot.findFirst({ orderBy: { date: "desc" } });
      const navPerUnit = snapshot?.navPerUnit ?? 100;
      const amount = pi.amount_received / 100; // cents to euros
      const units = amount / navPerUnit;

      // Create transaction record
      await prisma.transaction.create({
        data: {
          memberId,
          type: "subscribe",
          units,
          navPerUnit,
          amount,
          status: "completed",
        },
      });

      // Update member units and cost basis
      await prisma.member.update({
        where: { id: memberId },
        data: {
          units: { increment: units },
          costBasis: { increment: amount },
        },
      });

      break;
    }

    case "payment_intent.payment_failed": {
      const pi = event.data.object as Stripe.PaymentIntent;
      const memberId = pi.metadata.memberId;
      if (!memberId) break;

      // Find and mark the pending stripe subscription as failed
      await prisma.stripeSubscription.updateMany({
        where: { stripePaymentIntentId: pi.id, status: "pending" },
        data: { status: "failed" },
      });
      break;
    }
  }

  return NextResponse.json({ received: true });
}

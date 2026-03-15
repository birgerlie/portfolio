import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { requireAdmin } from "@/lib/admin";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET() {
  const auth = await requireAdmin();
  if (auth.error) return NextResponse.json({ error: auth.error }, { status: auth.status });

  const invites = await prisma.invite.findMany({
    orderBy: { sentAt: "desc" },
  });

  return NextResponse.json(invites);
}

export async function POST(req: Request) {
  const auth = await requireAdmin();
  if (auth.error) return NextResponse.json({ error: auth.error }, { status: auth.status });

  const { email, name } = await req.json();
  if (!email) return NextResponse.json({ error: "Email required" }, { status: 400 });

  // Use service role client to invite user
  const supabaseAdmin = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );

  const { data, error } = await supabaseAdmin.auth.admin.inviteUserByEmail(email, {
    redirectTo: `${process.env.NEXT_PUBLIC_SITE_URL || (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : new URL(req.url).origin)}/auth/callback`,
    data: { name: name || email.split("@")[0] },
  });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  // Persist the invite (best-effort — email was already sent)
  try {
    // Upsert: if a pending invite already exists for this email, update sentAt instead of creating a duplicate
    await prisma.invite.upsert({
      where: { email_status: { email, status: "pending" } },
      update: { sentAt: new Date(), name: name || "" },
      create: { email, name: name || "", status: "pending" },
    });
  } catch (e) {
    console.error("Failed to persist invite record:", e);
  }

  return NextResponse.json({ ok: true, userId: data.user.id });
}

import { createSupabaseServer } from "@/lib/supabase-server";
import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");

  const redirectUrl = process.env.NEXT_PUBLIC_SITE_URL || (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : origin);

  if (code) {
    const supabase = await createSupabaseServer();
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      try {
        const { data: { user } } = await supabase.auth.getUser();

        if (user) {
          // Auto-create Member record on first login
          const existing = await prisma.member.findUnique({
            where: { authId: user.id },
          });

          if (!existing) {
            const name = user.user_metadata?.name || user.email?.split("@")[0] || "Member";
            await prisma.member.create({
              data: {
                authId: user.id,
                email: user.email!,
                name,
              },
            });

            // Mark matching invite as accepted
            if (user.email) {
              await prisma.invite.updateMany({
                where: { email: user.email, status: "pending" },
                data: { status: "accepted", acceptedAt: new Date() },
              });
            }
          }
        }
      } catch (e) {
        console.error("Failed to auto-create member:", e);
      }
    }
  }

  return NextResponse.redirect(redirectUrl);
}

import { createSupabaseServer } from "./supabase-server";
import { prisma } from "./prisma";

const ADMIN_EMAILS = ["birger.lie@gmail.com"];

export async function requireAdmin() {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) return { error: "Not authenticated", status: 401, user: null, member: null };

  const member = await prisma.member.findUnique({ where: { authId: user.id } });
  const isAdmin = member?.role === "admin" || ADMIN_EMAILS.includes(user.email ?? "");

  if (!isAdmin) return { error: "Not authorized", status: 403, user, member };

  return { error: null, status: 200, user, member };
}

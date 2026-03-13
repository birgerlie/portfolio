import Link from "next/link";
import { EngineStatus } from "./engine-status";
import { createSupabaseServer } from "@/lib/supabase-server";
import { prisma } from "@/lib/prisma";

const ADMIN_EMAILS = ["birger.lie@gmail.com"];

export async function NavBar() {
  let isAdmin = false;
  try {
    const supabase = await createSupabaseServer();
    const { data: { user } } = await supabase.auth.getUser();
    if (user) {
      const member = await prisma.member.findUnique({ where: { authId: user.id } });
      isAdmin = member?.role === "admin" || ADMIN_EMAILS.includes(user.email ?? "");
    }
  } catch {
    // Not authenticated
  }

  return (
    <nav className="fixed top-0 w-full z-50 bg-black/80 backdrop-blur-xl border-b border-zinc-900">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        <Link href="/" className="text-sm font-medium text-white">
          Glass Box Fund
        </Link>
        <div className="flex items-center gap-6 text-sm text-zinc-400">
          <Link href="/universe" className="hover:text-white transition-colors">Universe</Link>
          <Link href="/journal" className="hover:text-white transition-colors">Journal</Link>
          <Link href="/reports" className="hover:text-white transition-colors">Reports</Link>
          <Link href="/invest" className="hover:text-white transition-colors">Invest</Link>
          <Link href="/admin" className="hover:text-white transition-colors">Admin</Link>
          <EngineStatus />
        </div>
      </div>
    </nav>
  );
}

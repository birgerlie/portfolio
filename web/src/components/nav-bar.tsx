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

  const linkClass = "text-white/45 hover:text-white/90 transition-colors px-2.5 py-1 rounded-[5px]";
  const activeLinkClass = "text-white/90 bg-white/[0.06] px-2.5 py-1 rounded-[5px]";

  return (
    <nav className="fixed top-0 w-full z-50 bg-[#0a0a0a]/80 backdrop-blur-xl border-b border-white/[0.06]">
      <div className="max-w-7xl mx-auto px-6 h-12 flex items-center justify-between">
        <Link href="/" className="text-[14px] font-semibold text-[#f5f5f5] tracking-[-0.01em]">
          Glass Box Fund
        </Link>
        <div className="flex items-center gap-0.5 text-[13px]">
          <Link href="/universe" className={linkClass}>Universe</Link>
          <Link href="/journal" className={linkClass}>Journal</Link>
          <Link href="/reports" className={linkClass}>Reports</Link>
          <Link href="/invest" className={linkClass}>Invest</Link>
          <Link href="/admin" className={linkClass}>Admin</Link>
          <div className="ml-3">
            <EngineStatus />
          </div>
        </div>
      </div>
    </nav>
  );
}

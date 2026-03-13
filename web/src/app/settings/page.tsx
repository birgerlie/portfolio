import { createSupabaseServer } from "@/lib/supabase-server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();
  const member = user ? await prisma.member.findUnique({ where: { authId: user.id } }) : null;

  return (
    <div className="min-h-screen pt-24 px-6 max-w-lg mx-auto">
      <h1 className="text-2xl font-medium tracking-tight mb-8">Settings</h1>
      <div className="space-y-5">
        <div>
          <label className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Email</label>
          <p className="text-[13px] text-[#f5f5f5] mt-1">{user?.email ?? "—"}</p>
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Name</label>
          <p className="text-[13px] text-[#f5f5f5] mt-1">{member?.name ?? "—"}</p>
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Member since</label>
          <p className="text-[13px] text-[#f5f5f5] mt-1">{member?.joinDate ? new Date(member.joinDate).toLocaleDateString() : "—"}</p>
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium">Role</label>
          <p className="text-[13px] text-[#f5f5f5] capitalize mt-1">{member?.role ?? "—"}</p>
        </div>
        <form action="/auth/signout" method="POST" className="pt-6">
          <button type="submit" className="px-5 py-2 bg-white/[0.06] border border-white/[0.06] rounded-lg text-[13px] text-white/65 hover:text-white/90 hover:bg-white/[0.1] transition-colors">Sign out</button>
        </form>
      </div>
    </div>
  );
}

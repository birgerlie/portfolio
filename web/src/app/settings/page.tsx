import { createSupabaseServer } from "@/lib/supabase-server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const supabase = await createSupabaseServer();
  const { data: { user } } = await supabase.auth.getUser();
  const member = user ? await prisma.member.findUnique({ where: { authId: user.id } }) : null;

  return (
    <div className="min-h-screen pt-28 px-6 max-w-lg mx-auto">
      <h1 className="text-4xl font-light mb-8">Settings</h1>
      <div className="space-y-6">
        <div><label className="text-sm text-zinc-500">Email</label><p className="text-white">{user?.email ?? "—"}</p></div>
        <div><label className="text-sm text-zinc-500">Name</label><p className="text-white">{member?.name ?? "—"}</p></div>
        <div><label className="text-sm text-zinc-500">Member since</label><p className="text-white">{member?.joinDate ? new Date(member.joinDate).toLocaleDateString() : "—"}</p></div>
        <div><label className="text-sm text-zinc-500">Role</label><p className="text-white capitalize">{member?.role ?? "—"}</p></div>
        <form action="/auth/signout" method="POST" className="pt-8">
          <button type="submit" className="px-6 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-400 hover:text-white transition-colors">Sign out</button>
        </form>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

interface Member {
  id: string;
  name: string;
  email: string;
  role: string;
  units: number;
  costBasis: number;
  joinDate: string;
  _count: { transactions: number };
}

export default function AdminPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState("");

  async function fetchMembers() {
    const res = await fetch("/api/admin/members");
    if (!res.ok) {
      setError(res.status === 401 ? "Not authenticated" : res.status === 403 ? "Not authorized" : "Failed to load");
      setLoading(false);
      return;
    }
    setMembers(await res.json());
    setLoading(false);
  }

  useEffect(() => { fetchMembers(); }, []);

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setInviteMsg("");
    const res = await fetch("/api/admin/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: inviteEmail, name: inviteName }),
    });
    const data = await res.json();
    if (res.ok) {
      setInviteMsg(`Magic link sent to ${inviteEmail}`);
      setInviteEmail("");
      setInviteName("");
    } else {
      setInviteMsg(`Error: ${data.error}`);
    }
    setInviting(false);
  }

  async function toggleRole(member: Member) {
    const newRole = member.role === "admin" ? "member" : "admin";
    await fetch("/api/admin/members", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: member.id, role: newRole }),
    });
    fetchMembers();
  }

  async function removeMember(member: Member) {
    if (!confirm(`Remove ${member.name} (${member.email})?`)) return;
    await fetch("/api/admin/members", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: member.id }),
    });
    fetchMembers();
  }

  if (loading) return <div className="min-h-screen pt-28 px-6 max-w-4xl mx-auto"><p className="text-zinc-500">Loading...</p></div>;
  if (error) return <div className="min-h-screen pt-28 px-6 max-w-4xl mx-auto"><p className="text-red-400">{error}</p></div>;

  return (
    <div className="min-h-screen pt-28 px-6 max-w-4xl mx-auto pb-20">
      <h1 className="text-4xl font-light mb-2">Admin</h1>
      <p className="text-zinc-500 mb-12">Manage members and send invitations</p>

      {/* Invite Section */}
      <div className="bg-zinc-900/50 rounded-2xl border border-zinc-800 p-6 mb-12">
        <h2 className="text-lg font-medium mb-4">Send Magic Link</h2>
        <form onSubmit={sendInvite} className="flex flex-col sm:flex-row gap-3">
          <input
            type="email" required placeholder="Email address" value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          />
          <input
            type="text" placeholder="Name (optional)" value={inviteName}
            onChange={(e) => setInviteName(e.target.value)}
            className="sm:w-48 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          />
          <button type="submit" disabled={inviting}
            className="bg-white text-black px-6 py-2 rounded-lg text-sm font-medium hover:bg-zinc-200 transition-colors disabled:opacity-50">
            {inviting ? "Sending..." : "Send Invite"}
          </button>
        </form>
        {inviteMsg && (
          <p className={`mt-3 text-sm ${inviteMsg.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
            {inviteMsg}
          </p>
        )}
      </div>

      {/* Members Table */}
      <h2 className="text-lg font-medium mb-4">Members ({members.length})</h2>
      {members.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-3 font-normal">Name</th>
              <th className="text-left py-3 font-normal">Email</th>
              <th className="text-left py-3 font-normal">Role</th>
              <th className="text-right py-3 font-normal">Units</th>
              <th className="text-right py-3 font-normal">Txns</th>
              <th className="text-right py-3 font-normal">Joined</th>
              <th className="text-right py-3 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} className="border-b border-zinc-800/50">
                <td className="py-3 font-medium">{m.name}</td>
                <td className="py-3 text-zinc-400">{m.email}</td>
                <td className="py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${m.role === "admin" ? "bg-blue-500/20 text-blue-400" : "bg-zinc-800 text-zinc-400"}`}>
                    {m.role}
                  </span>
                </td>
                <td className="text-right py-3 text-zinc-400">{m.units.toFixed(1)}</td>
                <td className="text-right py-3 text-zinc-400">{m._count.transactions}</td>
                <td className="text-right py-3 text-zinc-500">{new Date(m.joinDate).toLocaleDateString()}</td>
                <td className="text-right py-3 space-x-2">
                  <button onClick={() => toggleRole(m)} className="text-xs text-zinc-500 hover:text-white transition-colors">
                    {m.role === "admin" ? "Demote" : "Promote"}
                  </button>
                  <button onClick={() => removeMember(m)} className="text-xs text-zinc-500 hover:text-red-400 transition-colors">
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-zinc-600">No members yet. Send an invite to get started.</p>
      )}
    </div>
  );
}

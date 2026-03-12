import Link from "next/link";
import { EngineStatus } from "./engine-status";

export function NavBar() {
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
          <EngineStatus />
        </div>
      </div>
    </nav>
  );
}

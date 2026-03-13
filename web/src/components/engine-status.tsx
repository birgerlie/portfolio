"use client";

import { useEffect, useState } from "react";
import { createSupabaseBrowser } from "@/lib/supabase-client";

type Status = "running" | "degraded" | "stopped" | "unknown";

const statusColors: Record<Status, string> = {
  running: "bg-[#3dd68c]",
  degraded: "bg-yellow-500",
  stopped: "bg-[#f76e6e]",
  unknown: "bg-white/20",
};

const statusLabels: Record<Status, string> = {
  running: "Engine Running",
  degraded: "Engine Degraded",
  stopped: "Engine Offline",
  unknown: "Connecting...",
};

export function EngineStatus() {
  const [status, setStatus] = useState<Status>("unknown");

  useEffect(() => {
    const supabase = createSupabaseBrowser();

    supabase
      .from("engine_heartbeat")
      .select("status, updated_at")
      .eq("id", "singleton")
      .single()
      .then(({ data }) => {
        if (data) {
          const age = Date.now() - new Date(data.updated_at).getTime();
          if (age > 5 * 60 * 1000) setStatus("stopped");
          else setStatus(data.status as Status);
        }
      });

    const channel = supabase
      .channel("engine-heartbeat")
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "engine_heartbeat" },
        (payload) => {
          setStatus(payload.new.status as Status);
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  return (
    <div className="flex items-center gap-1.5 text-[12px]">
      <div className={`w-[6px] h-[6px] rounded-full ${statusColors[status]}`} />
      <span className="text-white/40">{statusLabels[status]}</span>
    </div>
  );
}

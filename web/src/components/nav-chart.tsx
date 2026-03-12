"use client";

import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip } from "recharts";

interface NavDataPoint {
  date: string;
  nav: number;
}

interface NavChartProps {
  data: NavDataPoint[];
}

export function NavChart({ data }: NavChartProps) {
  return (
    <div className="w-full h-64 mt-8">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="navGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            stroke="#3f3f46"
            tick={{ fill: "#71717a", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #27272a",
              borderRadius: "8px",
              color: "#fff",
            }}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter={((value: unknown) => [`€${Number(value ?? 0).toLocaleString()}`, "NAV"]) as any}
          />
          <Area
            type="monotone"
            dataKey="nav"
            stroke="#22c55e"
            strokeWidth={2}
            fill="url(#navGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

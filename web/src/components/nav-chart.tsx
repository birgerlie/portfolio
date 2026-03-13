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
              <stop offset="0%" stopColor="#3dd68c" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#3dd68c" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            stroke="rgba(255,255,255,0.06)"
            tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0a0a0a",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: "8px",
              color: "#f5f5f5",
              fontSize: "13px",
            }}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter={((value: unknown) => [`€${Number(value ?? 0).toLocaleString()}`, "NAV"]) as any}
          />
          <Area
            type="monotone"
            dataKey="nav"
            stroke="#3dd68c"
            strokeWidth={1.5}
            fill="url(#navGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

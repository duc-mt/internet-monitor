import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Measurement, Target } from "../types";
import { formatClock } from "../services/format";

const LINE_COLORS = ["#34d8c6", "#7c9eff", "#c792ea", "#5fd3f3", "#ff9f68", "#f472b6"];

export const RANGE_OPTIONS = [
  { label: "1m", minutes: 1 },
  { label: "5m", minutes: 5 },
  { label: "30m", minutes: 30 },
  { label: "1h", minutes: 60 },
] as const;

export type RangeMinutes = number;

interface Props {
  measurements: Measurement[];
  targets: Target[];
  rangeMinutes: RangeMinutes;
  onRangeChange: (m: RangeMinutes) => void;
  rangeOptions?: readonly { label: string; minutes: number }[];
}

export function LatencyChart({
  measurements,
  targets,
  rangeMinutes,
  onRangeChange,
  rangeOptions = RANGE_OPTIONS,
}: Props) {
  const seriesByTarget = useMemo(() => {
    const map = new Map<number, { ts: number; latency_ms: number | null }[]>();
    for (const t of targets) map.set(t.id, []);
    for (const m of measurements) {
      if (!map.has(m.target_id)) map.set(m.target_id, []);
      map.get(m.target_id)!.push({ ts: new Date(m.timestamp).getTime(), latency_ms: m.latency_ms });
    }
    for (const arr of map.values()) arr.sort((a, b) => a.ts - b.ts);
    return map;
  }, [measurements, targets]);

  const now = Date.now();
  const domainStart = now - rangeMinutes * 60_000;

  return (
    <div className="rounded-card border border-border bg-panel p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-text">Latency</h3>
        <div className="flex items-center rounded-control border border-border p-0.5 gap-0.5">
          {rangeOptions.map((opt) => (
            <button
              key={opt.label}
              onClick={() => onRangeChange(opt.minutes)}
              className={`px-2.5 py-1 text-xs rounded-[4px] font-mono transition-colors ${
                rangeMinutes === opt.minutes ? "bg-accent-soft text-accent" : "text-muted hover:text-text"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {measurements.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-sm text-muted">
          No measurements in this window yet.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="ts"
              type="number"
              domain={[domainStart, now]}
              tickFormatter={(v: number) => formatClock(new Date(v).toISOString())}
              stroke="var(--color-muted)"
              tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
              tickLine={false}
              axisLine={{ stroke: "var(--color-border)" }}
            />
            <YAxis
              unit=" ms"
              stroke="var(--color-muted)"
              tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
              tickLine={false}
              axisLine={false}
              width={56}
            />
            <Tooltip
              contentStyle={{
                background: "var(--color-panel-alt)",
                border: "1px solid var(--color-border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelFormatter={(v: number) => formatClock(new Date(v).toISOString())}
              formatter={(value: unknown) => [value === null ? "no response" : `${value} ms`, ""]}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "var(--color-muted)" }} />
            {targets.map((t, i) => (
              <Line
                key={t.id}
                data={seriesByTarget.get(t.id) ?? []}
                dataKey="latency_ms"
                name={t.name}
                stroke={LINE_COLORS[i % LINE_COLORS.length]}
                strokeWidth={1.75}
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

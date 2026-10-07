import { useMemo, useRef, useState } from "react";
import { Camera } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Measurement, Target } from "../types";
import { formatClock } from "../services/format";
import { buildSeries, buildTimeline } from "../services/chartData";
import { exportChartPng, formatStamp } from "../services/exportChart";
import { HoverTooltip } from "./HoverTooltip";

const LINE_COLORS = ["#34d8c6", "#7c9eff", "#c792ea", "#5fd3f3", "#ff9f68", "#f472b6"];
// Packet loss reads as "red" regardless of which targets are plotted.
const LOSS_COLOR = "#ef4444";

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
  const [showJitter, setShowJitter] = useState(true);
  const [showLoss, setShowLoss] = useState(true);

  const seriesByTarget = useMemo(() => buildSeries(measurements, targets), [measurements, targets]);
  const timeline = useMemo(() => buildTimeline(seriesByTarget), [seriesByTarget]);

  const now = Date.now();
  const domainStart = now - rangeMinutes * 60_000;

  const chartRef = useRef<HTMLDivElement>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = async () => {
    if (!chartRef.current) return;
    setExporting(true);
    setExportError(null);
    try {
      await exportChartPng(chartRef.current, {
        title: "Internet Monitor · Latency",
        subtitle: `${formatStamp(new Date(domainStart))}  →  ${formatStamp(new Date(now))}`,
        legend: [
          ...targets.map((t, i) => ({ label: t.name, color: LINE_COLORS[i % LINE_COLORS.length] })),
          ...(showJitter ? [{ label: "Jitter", color: "#94a3b8", style: "dashed" as const }] : []),
          ...(showLoss ? [{ label: "Packet loss", color: LOSS_COLOR, style: "block" as const }] : []),
        ],
      });
    } catch (err) {
      console.error("Chart export failed", err);
      setExportError("Could not export the chart · Không thể xuất biểu đồ.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="rounded-card border border-border bg-panel p-4 transition-all-fast">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold tracking-tight text-text">Latency · Biểu đồ độ trễ</h3>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowJitter((v) => !v)}
              aria-pressed={showJitter}
              title="Jitter (dashed line, same scale as latency)"
              className={`flex items-center gap-1.5 px-2 py-1 text-xs rounded-[4px] font-mono transition-all-fast ${
                showJitter ? "text-text" : "text-muted opacity-60 hover:opacity-100"
              }`}
            >
              <svg width="16" height="6" aria-hidden="true">
                <line x1="0" y1="3" x2="16" y2="3" stroke="var(--color-muted)" strokeWidth="1.5" strokeDasharray="3 3" />
              </svg>
              Jitter
            </button>
            <button
              onClick={() => setShowLoss((v) => !v)}
              aria-pressed={showLoss}
              title="Packet loss (red bars, 0-100%)"
              className={`flex items-center gap-1.5 px-2 py-1 text-xs rounded-[4px] font-mono transition-all-fast ${
                showLoss ? "text-text" : "text-muted opacity-60 hover:opacity-100"
              }`}
            >
              <span className="inline-block h-3 w-1.5 rounded-[1px]" style={{ background: LOSS_COLOR, opacity: 0.55 }} />
              Loss
            </button>
          </div>
          <button
            onClick={handleExport}
            disabled={exporting || measurements.length === 0}
            aria-label="Save chart as PNG"
            title="Save as PNG · Lưu biểu đồ thành ảnh"
            className="p-1.5 rounded-control border border-border bg-panel-alt text-muted hover:text-text transition-all-fast hover:-translate-y-1 disabled:opacity-40 disabled:hover:translate-y-0"
          >
            <Camera size={14} />
          </button>
          <div className="flex items-center rounded-control border border-border p-0.5 gap-0.5 bg-panel-alt">
            {rangeOptions.map((opt) => (
              <button
                key={opt.label}
                onClick={() => onRangeChange(opt.minutes)}
                className={`px-2.5 py-1 text-xs rounded-[4px] font-mono transition-all-fast ${
                  rangeMinutes === opt.minutes ? "bg-accent-soft text-accent font-semibold shadow-sm" : "text-muted hover:text-text"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {exportError && (
        <p className="mb-2 text-xs text-offline" role="alert">
          {exportError}
        </p>
      )}

      {measurements.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-sm text-muted">
          No measurements in this window yet · Chưa có dữ liệu đo lường trong khoảng thời gian này.
        </div>
      ) : (
        <div ref={chartRef}>
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={timeline} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="ts"
                type="number"
                domain={[domainStart, now]}
                tickFormatter={(v: number) => formatClock(new Date(v).toISOString())}
                stroke="var(--color-muted)"
                tick={{ fontSize: 11, fontFamily: "'Fira Code', monospace" }}
                tickLine={false}
                axisLine={{ stroke: "var(--color-border)" }}
              />
              <YAxis
                yAxisId="latency"
                unit=" ms"
                stroke="var(--color-muted)"
                tick={{ fontSize: 11, fontFamily: "'Fira Code', monospace" }}
                tickLine={false}
                axisLine={false}
                width={56}
              />
              {/* Hidden: it only fixes the packet-loss scale to 0-100% so a 100% bar spans the full plot height. */}
              <YAxis yAxisId="loss" orientation="right" domain={[0, 100]} hide />
              <Tooltip
                content={<HoverTooltip series={seriesByTarget} targets={targets} colors={LINE_COLORS} />}
                cursor={{ stroke: "var(--color-muted)", strokeDasharray: "3 3" }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: "var(--color-muted)" }} />
              {showLoss && (
                <Bar
                  yAxisId="loss"
                  dataKey="packet_loss"
                  name="Packet loss"
                  legendType="none"
                  fill={LOSS_COLOR}
                  fillOpacity={0.3}
                  barSize={3}
                  isAnimationActive={false}
                />
              )}
              {showJitter &&
                targets.map((t, i) => (
                  <Line
                    key={`jitter-${t.id}`}
                    yAxisId="latency"
                    data={seriesByTarget.get(t.id) ?? []}
                    dataKey="jitter_ms"
                    name={`${t.name} jitter`}
                    legendType="none"
                    stroke={LINE_COLORS[i % LINE_COLORS.length]}
                    strokeOpacity={0.55}
                    strokeWidth={1}
                    strokeDasharray="3 3"
                    dot={false}
                    activeDot={false}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                ))}
              {targets.map((t, i) => (
                <Line
                  key={t.id}
                  yAxisId="latency"
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
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

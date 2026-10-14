import { useMemo, useRef, useState } from "react";
import { Camera } from "lucide-react";
import { Area, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Measurement, Target } from "../types";
import { formatClock } from "../services/format";
import { buildSmokeSeries, formatMs, formatTick, type SmokePoint } from "../services/smokeData";
import { exportChartPng, formatStamp } from "../services/exportChart";

const LINE_COLOR = "#34d8c6";
// Packet loss reads as "red" whichever target is plotted.
const LOSS_COLOR = "#ef4444";
const IQR_OPACITY = 0.22;
const TAIL_OPACITY = 0.1;

export const SMOKE_RANGE_OPTIONS = [
  { label: "5m", minutes: 5 },
  { label: "15m", minutes: 15 },
  { label: "1h", minutes: 60 },
  { label: "6h", minutes: 360 },
  { label: "24h", minutes: 1440 },
] as const;

export type RangeMinutes = number;

interface Props {
  /** Measurements to draw; only the selected target's are used, so a list for several targets is fine. */
  measurements: Measurement[];
  targets: Target[];
  targetId: number | null;
  onTargetChange: (id: number) => void;
  rangeMinutes: RangeMinutes;
  onRangeChange: (m: RangeMinutes) => void;
  rangeOptions?: readonly { label: string; minutes: number }[];
  title?: string;
}

export function SmokeGraph({
  measurements,
  targets,
  targetId,
  onTargetChange,
  rangeMinutes,
  onRangeChange,
  rangeOptions = SMOKE_RANGE_OPTIONS,
  title = "Smoke graph · Biểu đồ độ trễ & biến động",
}: Props) {
  const [showLoss, setShowLoss] = useState(true);
  const chartRef = useRef<HTMLDivElement>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const now = Date.now();
  const domainStart = now - rangeMinutes * 60_000;
  const target = targets.find((t) => t.id === targetId) ?? null;

  const points = useMemo(
    () => buildSmokeSeries(measurements, { targetId, startMs: domainStart, endMs: now }),
    // `now` moves every render; the data only changes when the measurements / selection / window do.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [measurements, targetId, rangeMinutes],
  );
  const hasBands = points.some((p) => p.iqr !== null);

  const handleExport = async () => {
    if (!chartRef.current) return;
    setExporting(true);
    setExportError(null);
    try {
      await exportChartPng(chartRef.current, {
        title: `Internet Monitor · Smoke graph${target ? ` · ${target.name}` : ""}`,
        subtitle: `${formatStamp(new Date(domainStart))}  →  ${formatStamp(new Date(now))}`,
        legend: [
          { label: "Median", color: LINE_COLOR },
          { label: "IQR (p25–p75)", color: LINE_COLOR, style: "block" as const },
          { label: "Tail (min–p95)", color: "#8ee9de", style: "block" as const },
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
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="text-sm font-semibold tracking-tight text-text">{title}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Target"
            value={targetId ?? ""}
            onChange={(e) => onTargetChange(Number(e.target.value))}
            className="rounded-control border border-border bg-panel-alt px-2.5 py-1 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent transition-all-fast"
          >
            {targets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
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
          <button
            onClick={handleExport}
            disabled={exporting || points.length === 0}
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
                aria-pressed={rangeMinutes === opt.minutes}
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

      <SmokeLegend showLoss={showLoss} />

      {exportError && (
        <p className="mb-2 text-xs text-offline" role="alert">
          {exportError}
        </p>
      )}

      {points.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-sm text-muted text-center px-4">
          No measurements in this window yet — a burst is recorded every minute by default · Chưa có dữ liệu đo lường trong khoảng thời
          gian này.
        </div>
      ) : (
        <div ref={chartRef}>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={points} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="ts"
                type="number"
                domain={[domainStart, now]}
                tickFormatter={(v: number) => formatTick(v, rangeMinutes)}
                stroke="var(--color-muted)"
                tick={{ fontSize: 11, fontFamily: "'Fira Code', monospace" }}
                tickLine={false}
                axisLine={{ stroke: "var(--color-border)" }}
              />
              <YAxis
                yAxisId="latency"
                unit=" ms"
                domain={[0, "auto"]}
                stroke="var(--color-muted)"
                tick={{ fontSize: 11, fontFamily: "'Fira Code', monospace" }}
                tickLine={false}
                axisLine={false}
                width={56}
              />
              {/* Hidden: only fixes the loss scale to 0-100% so a 100% bar spans the plot height. */}
              <YAxis yAxisId="loss" orientation="right" domain={[0, 100]} hide />
              <Tooltip content={<SmokeTooltip />} cursor={{ stroke: "var(--color-muted)", strokeDasharray: "3 3" }} />
              {showLoss && (
                <Bar yAxisId="loss" dataKey="loss" name="Packet loss" fill={LOSS_COLOR} fillOpacity={0.3} barSize={3} isAnimationActive={false} />
              )}
              {/* Outer band first so the inner one is drawn on top of it. */}
              <Area
                yAxisId="latency"
                dataKey="tail"
                name="Tail (min–p95)"
                type="monotone"
                stroke="none"
                fill={LINE_COLOR}
                fillOpacity={TAIL_OPACITY}
                isAnimationActive={false}
                connectNulls={false}
                activeDot={false}
              />
              {hasBands && (
                <Area
                  yAxisId="latency"
                  dataKey="iqr"
                  name="IQR (p25–p75)"
                  type="monotone"
                  stroke="none"
                  fill={LINE_COLOR}
                  fillOpacity={IQR_OPACITY}
                  isAnimationActive={false}
                  connectNulls={false}
                  activeDot={false}
                />
              )}
              <Line
                yAxisId="latency"
                dataKey="median"
                name="Median"
                type="monotone"
                stroke={LINE_COLOR}
                strokeWidth={1.75}
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function SmokeLegend({ showLoss }: { showLoss: boolean }) {
  const swatch = (opacity: number) => (
    <span className="inline-block h-2.5 w-4 rounded-[2px]" style={{ background: LINE_COLOR, opacity }} aria-hidden="true" />
  );
  return (
    <ul className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-muted" aria-label="Chart legend">
      <li className="flex items-center gap-1.5">
        <span className="inline-block h-0.5 w-4" style={{ background: LINE_COLOR }} aria-hidden="true" />
        Median
      </li>
      <li className="flex items-center gap-1.5">
        {swatch(IQR_OPACITY + 0.15)}
        IQR p25–p75
      </li>
      <li className="flex items-center gap-1.5">
        {swatch(TAIL_OPACITY + 0.1)}
        Tail min–p95
      </li>
      {showLoss && (
        <li className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-1.5 rounded-[1px]" style={{ background: LOSS_COLOR, opacity: 0.55 }} aria-hidden="true" />
          Packet loss
        </li>
      )}
    </ul>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: SmokePoint }[];
}

export function SmokeTooltip({ active, payload }: TooltipProps) {
  const p = active && payload && payload.length > 0 ? payload[0].payload : null;
  if (!p) return null;
  const rows: [string, string][] = [
    ["Median", formatMs(p.median)],
    ["IQR", formatMs(p.iqrMs)],
    ["p95", formatMs(p.p95)],
    ["Min / Max", `${formatMs(p.min)} / ${formatMs(p.max)}`],
    ["Jitter", formatMs(p.jitter, 2)],
    ["Loss", p.loss === null ? "0%" : `${p.loss.toFixed(1)}%`],
  ];
  return (
    <div className="rounded-control border border-border bg-panel px-3 py-2 text-xs shadow-lg">
      <p className="font-mono text-muted mb-1">
        {formatClock(new Date(p.ts).toISOString())}
        {p.samples > 1 && <span> · {p.samples} checks</span>}
      </p>
      <dl className="grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5 font-mono">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted">{label}</dt>
            <dd className="text-text text-right font-tabular">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

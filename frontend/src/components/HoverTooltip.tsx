import type { Target } from "../types";
import { formatClock, formatLatency, formatPct } from "../services/format";
import { hoverToleranceMs, nearestPoint, type ChartPoint } from "../services/chartData";

interface Props {
  // Injected by Recharts when this element is used as Tooltip `content`.
  active?: boolean;
  label?: number | string;
  // Ours.
  series: Map<number, ChartPoint[]>;
  targets: Target[];
  colors: string[];
}

/**
 * Latency, jitter and packet loss for every target at the hovered time.
 *
 * Recharts' default tooltip indexes each line's own data by the hovered
 * position, which lines up only when all series share timestamps; targets are
 * pinged independently, so each row here is looked up by time instead.
 */
export function HoverTooltip({ active, label, series, targets, colors }: Props) {
  if (!active || typeof label !== "number") return null;

  const rows = targets
    .map((target, i) => {
      const points = series.get(target.id) ?? [];
      const point = nearestPoint(points, label, hoverToleranceMs(points));
      return point ? { target, point, color: colors[i % colors.length] } : null;
    })
    .filter((row): row is { target: Target; point: ChartPoint; color: string } => row !== null);

  if (rows.length === 0) return null;

  return (
    <div className="rounded-control border border-border bg-panel-alt px-3 py-2 text-xs shadow-lg">
      <p className="font-mono text-muted mb-1.5">{formatClock(new Date(label).toISOString())}</p>
      <div className="space-y-2">
        {rows.map(({ target, point, color }) => (
          <div key={target.id}>
            <p className="flex items-center gap-1.5 font-semibold text-text">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
              {target.name}
            </p>
            <dl className="mt-0.5 grid grid-cols-[auto_1fr] gap-x-3 font-mono font-tabular text-[11px]">
              <dt className="text-muted">Latency</dt>
              <dd className={`text-right ${point.latency_ms === null ? "text-offline" : "text-text"}`}>
                {point.latency_ms === null ? "no response" : formatLatency(point.latency_ms)}
              </dd>
              <dt className="text-muted">Jitter</dt>
              <dd className="text-right text-text">{formatLatency(point.jitter_ms)}</dd>
              <dt className="text-muted">Packet loss</dt>
              <dd className={`text-right ${point.packet_loss > 0 ? "text-offline" : "text-text"}`}>
                {formatPct(point.packet_loss)}
              </dd>
            </dl>
          </div>
        ))}
      </div>
    </div>
  );
}

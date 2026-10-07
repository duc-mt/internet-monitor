import type { Measurement, Target } from "../types";

export interface ChartPoint {
  ts: number;
  latency_ms: number | null;
  jitter_ms: number | null;
  /** 0-100 for this single check; 100 means every probe was lost. */
  packet_loss: number;
}

/** One row of the chart-level dataset: a check from any target at time `ts`. */
export interface TimelineRow {
  ts: number;
  /** The check's packet loss, or null when it lost nothing (so no bar is drawn). */
  packet_loss: number | null;
}

/** Measurements grouped per target and sorted by time. Every target gets an entry, even with no data. */
export function buildSeries(measurements: Measurement[], targets: Target[]): Map<number, ChartPoint[]> {
  const map = new Map<number, ChartPoint[]>();
  for (const t of targets) map.set(t.id, []);
  for (const m of measurements) {
    if (!map.has(m.target_id)) map.set(m.target_id, []);
    map.get(m.target_id)!.push({
      ts: new Date(m.timestamp).getTime(),
      latency_ms: m.latency_ms,
      jitter_ms: m.jitter_ms,
      packet_loss: m.packet_loss,
    });
  }
  for (const arr of map.values()) arr.sort((a, b) => a.ts - b.ts);
  return map;
}

/**
 * Every check from every plotted target, in time order. This is the
 * chart-level dataset, for two reasons: Recharts' <Bar> (unlike <Line>) can
 * only read the chart's own data, and the hover tooltip snaps to the x values
 * of that dataset, so it lands on real measurement times. Loss is null when a
 * check lost nothing so only the red bars of checks that did lose packets are
 * drawn.
 */
export function buildTimeline(series: Map<number, ChartPoint[]>): TimelineRow[] {
  const rows: TimelineRow[] = [];
  for (const points of series.values()) {
    for (const p of points) rows.push({ ts: p.ts, packet_loss: p.packet_loss > 0 ? p.packet_loss : null });
  }
  return rows.sort((a, b) => a.ts - b.ts);
}

/** How far from a hovered time a sample may be and still count as "the" sample there. */
export function hoverToleranceMs(points: ChartPoint[]): number {
  if (points.length < 2) return 5000;
  const gaps: number[] = [];
  for (let i = 1; i < points.length; i++) gaps.push(points[i].ts - points[i - 1].ts);
  gaps.sort((a, b) => a - b);
  const median = gaps[Math.floor(gaps.length / 2)];
  return Math.max(2000, median * 1.5);
}

/** The sample closest to `ts` within `toleranceMs`, or null. `points` must be sorted by ts. */
export function nearestPoint(points: ChartPoint[], ts: number, toleranceMs: number): ChartPoint | null {
  if (points.length === 0) return null;
  let lo = 0;
  let hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid].ts < ts) lo = mid + 1;
    else hi = mid;
  }
  // `lo` is the first point at/after ts; the closest one is it or its predecessor.
  let best = points[lo];
  if (lo > 0 && Math.abs(points[lo - 1].ts - ts) <= Math.abs(best.ts - ts)) best = points[lo - 1];
  return Math.abs(best.ts - ts) <= toleranceMs ? best : null;
}

import type { Measurement } from "../types";

/**
 * Data layer for the Smoke Graph (SmokePing-style range chart): one hovered
 * time = one burst, drawn as a median line over two translucent bands.
 *
 *   inner band  p25 -> p75   the interquartile range: where the typical packet lands
 *   outer band  min -> p95   the tail: the slow packets the median hides
 *
 * Pure functions, so the awkward parts (legacy rows without burst data, hourly
 * rollup rows, thinning a 30-day range to a drawable number of points) are
 * unit-tested without a browser.
 */

export interface SmokePoint {
  ts: number;
  median: number | null;
  /** [p25, p75] - null when the burst has no spread information (a pre-upgrade row). */
  iqr: [number, number] | null;
  /** [min, p95] - the tail band. */
  tail: [number, number] | null;
  iqrMs: number | null;
  p95: number | null;
  min: number | null;
  max: number | null;
  jitter: number | null;
  /** 0-100 for this point, or null when nothing was lost (so no loss bar is drawn). */
  loss: number | null;
  /** Number of checks this point stands for: 1 for a raw check, more for a bucket / hourly rollup. */
  samples: number;
}

/** What the backend marks hourly rollup rows with (see measurements_repo.DOWNSAMPLED_MARKER). */
export const DOWNSAMPLED_MARKER = "Downsampled";

const finite = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** One measurement as a smoke point. Rows without burst columns degrade to a bare median line. */
export function toSmokePoint(m: Measurement): SmokePoint {
  const median = finite(m.median_ms) ? m.median_ms : finite(m.latency_ms) ? m.latency_ms : null;
  const iqrMs = finite(m.iqr_ms) ? m.iqr_ms : null;
  // Hourly rollup rows keep the average IQR but not the quartiles themselves: centre it on the median.
  const p25 = finite(m.p25_ms) ? m.p25_ms : median !== null && iqrMs !== null ? median - iqrMs / 2 : null;
  const p75 = finite(m.p75_ms) ? m.p75_ms : median !== null && iqrMs !== null ? median + iqrMs / 2 : null;
  const min = finite(m.min_ms) ? m.min_ms : null;
  const p95 = finite(m.p95_ms) ? m.p95_ms : null;
  const lo = min ?? p25;
  const hi = p95 ?? p75;
  return {
    ts: new Date(m.timestamp).getTime(),
    median,
    iqr: p25 !== null && p75 !== null ? [p25, p75] : null,
    tail: lo !== null && hi !== null ? [lo, hi] : null,
    iqrMs,
    p95,
    min,
    max: finite(m.max_ms) ? m.max_ms : null,
    jitter: finite(m.jitter_rfc3550) ? m.jitter_rfc3550 : finite(m.jitter_ms) ? m.jitter_ms : null,
    loss: m.packet_loss > 0 ? m.packet_loss : null,
    samples: 1,
  };
}

const mean = (values: number[]): number | null => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);

function medianOf(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

const defined = (values: (number | null)[]): number[] => values.filter(finite);

/**
 * Folds several points into one. Mirrors how SmokePing consolidates: the line is
 * the median of the medians, the quartiles are averaged, and the tail keeps its
 * extremes (lowest min, highest p95) - a spike must never be averaged away just
 * because the range being viewed is long.
 */
export function mergePoints(points: SmokePoint[]): SmokePoint {
  const ts = Math.round(mean(points.map((p) => p.ts)) ?? points[0].ts);
  const p25 = mean(defined(points.map((p) => p.iqr?.[0] ?? null)));
  const p75 = mean(defined(points.map((p) => p.iqr?.[1] ?? null)));
  const mins = defined(points.map((p) => p.min ?? p.tail?.[0] ?? null));
  const p95s = defined(points.map((p) => p.p95 ?? p.tail?.[1] ?? null));
  const lowest = mins.length ? Math.min(...mins) : null;
  const highest = p95s.length ? Math.max(...p95s) : null;
  const maxes = defined(points.map((p) => p.max));
  const losses = points.map((p) => p.loss ?? 0);
  const avgLoss = mean(losses) ?? 0;
  const lo = lowest ?? p25;
  const hi = highest ?? p75;
  return {
    ts,
    median: medianOf(defined(points.map((p) => p.median))),
    iqr: p25 !== null && p75 !== null ? [p25, p75] : null,
    tail: lo !== null && hi !== null ? [lo, hi] : null,
    iqrMs: mean(defined(points.map((p) => p.iqrMs))),
    p95: highest,
    min: lowest,
    max: maxes.length ? Math.max(...maxes) : null,
    jitter: mean(defined(points.map((p) => p.jitter))),
    loss: avgLoss > 0 ? avgLoss : null,
    samples: points.reduce((n, p) => n + p.samples, 0),
  };
}

export interface SmokeOptions {
  /** Only this target's measurements are used (a smoke graph is one target at a time). */
  targetId: number | null;
  startMs: number;
  endMs: number;
  /** Above this many points the series is thinned into equal time buckets. */
  maxPoints?: number;
}

export const DEFAULT_MAX_POINTS = 480;

/**
 * Measurements of one target inside the window, oldest first, thinned to at most
 * `maxPoints` (so a 30-day view of 1-minute checks - 43,200 of them - stays a
 * drawable, hoverable chart).
 */
export function buildSmokeSeries(measurements: Measurement[], opts: SmokeOptions): SmokePoint[] {
  const { targetId, startMs, endMs, maxPoints = DEFAULT_MAX_POINTS } = opts;
  const points = measurements
    .filter((m) => targetId === null || m.target_id === targetId)
    .map(toSmokePoint)
    .filter((p) => Number.isFinite(p.ts) && p.ts >= startMs && p.ts <= endMs)
    .sort((a, b) => a.ts - b.ts);
  if (points.length <= maxPoints) return points;

  const width = Math.max(1, Math.ceil((endMs - startMs) / maxPoints));
  const buckets = new Map<number, SmokePoint[]>();
  for (const p of points) {
    const key = Math.floor((p.ts - startMs) / width);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(p);
    else buckets.set(key, [p]);
  }
  return [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([, group]) => (group.length === 1 ? group[0] : mergePoints(group)));
}

/** The target a smoke graph opens on: the first enabled non-gateway target (the internet), else the first enabled one. */
export function defaultSmokeTargetId(targets: { id: number; enabled: boolean; is_gateway: boolean }[]): number | null {
  const enabled = targets.filter((t) => t.enabled);
  return (enabled.find((t) => !t.is_gateway) ?? enabled[0])?.id ?? null;
}

export function formatMs(v: number | null, digits = 1): string {
  return v === null ? "—" : `${v.toFixed(digits)} ms`;
}

/**
 * X-axis label for a time. A bare clock reading is right for a window of hours
 * but meaningless across days, so: up to 6h -> "14:05", up to 48h -> "Oct 14 14:05",
 * longer -> "Oct 14".
 */
export function formatTick(ms: number, rangeMinutes: number, locale?: string): string {
  const d = new Date(ms);
  if (rangeMinutes > 2880) return d.toLocaleDateString(locale, { month: "short", day: "numeric" });
  const clock = d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", hour12: false });
  if (rangeMinutes > 360) return `${d.toLocaleDateString(locale, { month: "short", day: "numeric" })} ${clock}`;
  return clock;
}

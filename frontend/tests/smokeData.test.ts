import { describe, expect, it } from "vitest";
import {
  buildSmokeSeries,
  defaultSmokeTargetId,
  formatMs,
  formatTick,
  mergePoints,
  toSmokePoint,
  type SmokePoint,
} from "../src/services/smokeData";
import type { Measurement } from "../src/types";

const T0 = Date.parse("2026-10-14T00:00:00Z");
const iso = (offsetSeconds: number) => new Date(T0 + offsetSeconds * 1000).toISOString();

function burst(offset: number, over: Partial<Measurement> = {}, target_id = 1): Measurement {
  return {
    id: offset + 1,
    target_id,
    timestamp: iso(offset),
    latency_ms: 20,
    packet_loss: 0,
    jitter_ms: 1,
    success: true,
    error: null,
    median_ms: 20,
    p25_ms: 18,
    p75_ms: 23,
    p95_ms: 40,
    min_ms: 15,
    max_ms: 55,
    iqr_ms: 5,
    jitter_rfc3550: 0.8,
    packet_count: 15,
    ...over,
  };
}

describe("toSmokePoint", () => {
  it("maps a burst to a median, an IQR band and a tail band", () => {
    const p = toSmokePoint(burst(0));
    expect(p.median).toBe(20);
    expect(p.iqr).toEqual([18, 23]);
    expect(p.tail).toEqual([15, 40]);
    expect(p).toMatchObject({ iqrMs: 5, p95: 40, min: 15, max: 55, jitter: 0.8, loss: null, samples: 1 });
  });

  it("prefers the RFC 3550 jitter and keeps loss only when something was lost", () => {
    expect(toSmokePoint(burst(0, { jitter_rfc3550: 2.5, jitter_ms: 9 })).jitter).toBe(2.5);
    expect(toSmokePoint(burst(0, { packet_loss: 6.67 })).loss).toBe(6.67);
  });

  it("degrades a pre-upgrade row to a bare median line, without invented bands", () => {
    const legacy: Measurement = {
      id: 1, target_id: 1, timestamp: iso(0), latency_ms: 31, packet_loss: 0, jitter_ms: 2, success: true, error: null,
    };
    const p = toSmokePoint(legacy);
    expect(p.median).toBe(31);
    expect(p.iqr).toBeNull();
    expect(p.tail).toBeNull();
    expect(p.jitter).toBe(2);
  });

  it("centres the band on the median for hourly rollup rows, which only keep the average IQR", () => {
    const hourly = burst(0, { p25_ms: null, p75_ms: null, median_ms: 30, iqr_ms: 8, error: "Downsampled" });
    expect(toSmokePoint(hourly).iqr).toEqual([26, 34]);
  });

  it("draws nothing for a burst where every probe was lost", () => {
    const dead = burst(0, {
      latency_ms: null, median_ms: null, p25_ms: null, p75_ms: null, p95_ms: null, min_ms: null, max_ms: null,
      iqr_ms: null, jitter_rfc3550: null, jitter_ms: null, packet_loss: 100, success: false,
    });
    const p = toSmokePoint(dead);
    expect(p).toMatchObject({ median: null, iqr: null, tail: null, loss: 100 });
  });
});

describe("buildSmokeSeries", () => {
  const opts = { targetId: 1, startMs: T0, endMs: T0 + 3600_000 };

  it("keeps only the selected target, inside the window, oldest first", () => {
    const rows = [burst(300), burst(60), burst(120, {}, 2), burst(-500), burst(7200)];
    const series = buildSmokeSeries(rows, opts);
    expect(series.map((p) => p.ts - T0)).toEqual([60_000, 300_000]);
  });

  it("returns every point when there are few enough", () => {
    const rows = Array.from({ length: 50 }, (_, i) => burst(i * 60));
    expect(buildSmokeSeries(rows, { ...opts, maxPoints: 480 })).toHaveLength(50);
  });

  it("thins a long series into time buckets of at most maxPoints", () => {
    // 30 days of one check a minute
    const month = 30 * 24 * 3600_000;
    const rows = Array.from({ length: 43_200 }, (_, i) => burst(i * 60));
    const series = buildSmokeSeries(rows, { targetId: 1, startMs: T0, endMs: T0 + month, maxPoints: 480 });
    expect(series.length).toBeLessThanOrEqual(480);
    expect(series.length).toBeGreaterThan(400);
    expect(series.reduce((n, p) => n + p.samples, 0)).toBe(43_200); // nothing dropped, only merged
    expect(series.every((p, i) => i === 0 || p.ts > series[i - 1].ts)).toBe(true);
  });

  it("does not average a latency spike away when thinning", () => {
    const rows = Array.from({ length: 1000 }, (_, i) => burst(i * 3));
    rows[500] = burst(1500, { median_ms: 21, p95_ms: 480, max_ms: 900, packet_loss: 20 });
    const series = buildSmokeSeries(rows, { targetId: 1, startMs: T0, endMs: T0 + 3000_000, maxPoints: 20 });
    expect(Math.max(...series.map((p) => p.p95 ?? 0))).toBe(480);
    expect(Math.max(...series.map((p) => p.max ?? 0))).toBe(900);
    expect(series.some((p) => (p.loss ?? 0) > 0)).toBe(true);
  });

  it("returns nothing for no data", () => {
    expect(buildSmokeSeries([], opts)).toEqual([]);
  });
});

describe("mergePoints", () => {
  const mk = (over: Partial<SmokePoint>): SmokePoint => ({
    ts: T0, median: 10, iqr: [9, 12], tail: [8, 20], iqrMs: 3, p95: 20, min: 8, max: 30, jitter: 1, loss: null, samples: 1, ...over,
  });

  it("takes the median of medians, averages the quartiles and keeps the tail extremes", () => {
    const merged = mergePoints([
      mk({ median: 10, iqr: [8, 12], min: 7, p95: 20 }),
      mk({ median: 12, iqr: [10, 14], min: 9, p95: 25 }),
      mk({ median: 100, iqr: [60, 140], min: 50, p95: 300 }),
    ]);
    expect(merged.median).toBe(12);
    expect(merged.iqr?.[0]).toBeCloseTo(26, 10); // (8 + 10 + 60) / 3
    expect(merged.iqr?.[1]).toBeCloseTo(166 / 3, 10); // (12 + 14 + 140) / 3
    expect(merged.min).toBe(7);
    expect(merged.p95).toBe(300);
    expect(merged.samples).toBe(3);
  });

  it("averages loss across the merged points", () => {
    const merged = mergePoints([mk({ loss: 20 }), mk({ loss: null }), mk({ loss: null }), mk({ loss: null })]);
    expect(merged.loss).toBe(5);
    expect(mergePoints([mk({}), mk({})]).loss).toBeNull();
  });

  it("copes with points that have no spread information", () => {
    const bare = mk({ iqr: null, tail: null, iqrMs: null, p95: null, min: null, max: null });
    const merged = mergePoints([bare, bare]);
    expect(merged.iqr).toBeNull();
    expect(merged.tail).toBeNull();
    expect(merged.median).toBe(10);
  });
});

describe("helpers", () => {
  it("opens on the first enabled non-gateway target", () => {
    const targets = [
      { id: 1, enabled: true, is_gateway: true },
      { id: 2, enabled: false, is_gateway: false },
      { id: 3, enabled: true, is_gateway: false },
    ];
    expect(defaultSmokeTargetId(targets)).toBe(3);
    expect(defaultSmokeTargetId(targets.filter((t) => t.is_gateway))).toBe(1);
    expect(defaultSmokeTargetId([])).toBeNull();
  });

  it("labels the time axis with a date once the window is longer than a few hours", () => {
    const t = new Date(2026, 9, 14, 14, 5).getTime(); // local time, so the assertions hold in any timezone
    expect(formatTick(t, 60, "en-US")).toBe("14:05");
    expect(formatTick(t, 360, "en-US")).toBe("14:05");
    expect(formatTick(t, 1440, "en-US")).toBe("Oct 14 14:05");
    expect(formatTick(t, 43200, "en-US")).toBe("Oct 14");
  });

  it("formats milliseconds", () => {
    expect(formatMs(12.345)).toBe("12.3 ms");
    expect(formatMs(1.234, 2)).toBe("1.23 ms");
    expect(formatMs(null)).toBe("—");
  });
});

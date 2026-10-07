import { describe, expect, it } from "vitest";
import { buildSeries, buildTimeline, hoverToleranceMs, nearestPoint, type ChartPoint } from "../src/services/chartData";
import type { Measurement, Target } from "../src/types";

const T0 = Date.parse("2026-01-01T00:00:00Z");
const iso = (offsetSeconds: number) => new Date(T0 + offsetSeconds * 1000).toISOString();

const targets = [
  { id: 1, name: "Gateway", host: "192.168.1.1" },
  { id: 2, name: "Cloudflare DNS", host: "1.1.1.1" },
] as Target[];

function m(id: number, target_id: number, offset: number, latency: number | null, loss: number, jitter: number | null): Measurement {
  return {
    id, target_id, timestamp: iso(offset), latency_ms: latency, packet_loss: loss, jitter_ms: jitter,
    success: loss < 100, error: null,
  };
}

describe("buildSeries", () => {
  it("groups by target, sorts by time and carries jitter and loss", () => {
    const series = buildSeries(
      [m(3, 1, 20, 5, 0, 0.5), m(1, 1, 0, 4, 0, 0.4), m(2, 2, 10, null, 100, null)],
      targets
    );
    expect(series.get(1)?.map((p) => p.ts - T0)).toEqual([0, 20000]);
    expect(series.get(1)?.[0].jitter_ms).toBe(0.4);
    expect(series.get(2)?.[0].latency_ms).toBeNull();
    expect(series.get(2)?.[0].packet_loss).toBe(100);
  });

  it("gives targets with no data an empty series", () => {
    expect(buildSeries([], targets).get(2)).toEqual([]);
  });
});

describe("buildTimeline", () => {
  it("merges every target's checks in time order, with loss only where packets were lost", () => {
    const series = buildSeries([m(1, 1, 0, 4, 0, 0.4), m(2, 2, 5, 20, 33, 1), m(3, 1, 10, null, 100, null)], targets);
    expect(buildTimeline(series).map((r) => [r.ts - T0, r.packet_loss])).toEqual([
      [0, null],
      [5000, 33],
      [10000, 100],
    ]);
  });
});

describe("nearestPoint", () => {
  const point = (offset: number): ChartPoint => ({ ts: T0 + offset * 1000, latency_ms: offset, jitter_ms: null, packet_loss: 0 });
  const points = [0, 10, 20, 30].map(point);

  it("returns the closest sample on either side", () => {
    expect(nearestPoint(points, T0 + 12_000, 5000)?.latency_ms).toBe(10);
    expect(nearestPoint(points, T0 + 17_000, 5000)?.latency_ms).toBe(20);
  });

  it("handles the ends and exact hits", () => {
    expect(nearestPoint(points, T0 - 1000, 5000)?.latency_ms).toBe(0);
    expect(nearestPoint(points, T0 + 31_000, 5000)?.latency_ms).toBe(30);
    expect(nearestPoint(points, T0 + 20_000, 5000)?.latency_ms).toBe(20);
  });

  it("returns null when nothing is within tolerance, or there are no points", () => {
    expect(nearestPoint(points, T0 + 100_000, 5000)).toBeNull();
    expect(nearestPoint([], T0, 5000)).toBeNull();
  });
});

describe("hoverToleranceMs", () => {
  const spaced = (gapSeconds: number, count: number): ChartPoint[] =>
    Array.from({ length: count }, (_, i) => ({ ts: T0 + i * gapSeconds * 1000, latency_ms: 1, jitter_ms: null, packet_loss: 0 }));

  it("is 1.5x the typical gap, so a slow target still resolves under the cursor", () => {
    expect(hoverToleranceMs(spaced(60, 5))).toBe(90000);
  });

  it("never drops below 2 s and has a default for tiny series", () => {
    expect(hoverToleranceMs(spaced(1, 5))).toBe(2000);
    expect(hoverToleranceMs(spaced(5, 1))).toBe(5000);
  });
});

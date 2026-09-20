import { describe, expect, it } from "vitest";
import { formatDuration, formatLatency, formatPct } from "../src/services/format";

describe("formatLatency", () => {
  it("renders a dash for null/undefined", () => {
    expect(formatLatency(null)).toBe("—");
    expect(formatLatency(undefined)).toBe("—");
  });
  it("formats sub-10ms with two decimals", () => {
    expect(formatLatency(3.14159)).toBe("3.14 ms");
  });
  it("formats larger values with one decimal", () => {
    expect(formatLatency(123.456)).toBe("123.5 ms");
  });
});

describe("formatPct", () => {
  it("renders a dash for null", () => {
    expect(formatPct(null)).toBe("—");
  });
  it("formats one decimal place", () => {
    expect(formatPct(12.345)).toBe("12.3%");
  });
});

describe("formatDuration", () => {
  it("renders a dash for null", () => {
    expect(formatDuration(null)).toBe("—");
  });
  it("formats seconds only", () => {
    expect(formatDuration(42)).toBe("42s");
  });
  it("formats minutes and seconds", () => {
    expect(formatDuration(125)).toBe("2m 5s");
  });
  it("formats hours and minutes", () => {
    expect(formatDuration(3700)).toBe("1h 1m");
  });
  it("formats days and hours", () => {
    expect(formatDuration(90000)).toBe("1d 1h");
  });
  it("clamps negative values to zero", () => {
    expect(formatDuration(-5)).toBe("0s");
  });
});

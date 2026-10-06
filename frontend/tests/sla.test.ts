import { describe, expect, it } from "vitest";
import { allowedDowntimeSeconds, computeErrorBudget } from "../src/services/sla";

const THIRTY_DAYS = 30 * 86400;

describe("computeErrorBudget", () => {
  it("allows 43m 12s of downtime per 30 days at 99.9%", () => {
    const budget = computeErrorBudget(THIRTY_DAYS, 0, 99.9);
    expect(budget?.allowedSeconds).toBe(2592);
    expect(budget?.status).toBe("ok");
    expect(budget?.usedPct).toBe(0);
  });

  it("stays ok while well inside the budget", () => {
    const budget = computeErrorBudget(THIRTY_DAYS, 300, 99.9);
    expect(budget?.status).toBe("ok");
    expect(budget?.remainingSeconds).toBe(2292);
    expect(budget?.usedPct).toBeCloseTo(11.57, 1);
  });

  it("warns once 80% of the budget is used", () => {
    expect(computeErrorBudget(THIRTY_DAYS, 2000, 99.9)?.status).toBe("ok"); // 77%
    expect(computeErrorBudget(THIRTY_DAYS, 2200, 99.9)?.status).toBe("warning"); // 85%
  });

  it("is breached only when downtime exceeds the allowance", () => {
    expect(computeErrorBudget(THIRTY_DAYS, 2592, 99.9)?.status).toBe("warning"); // exactly spent, not over
    const over = computeErrorBudget(THIRTY_DAYS, 3000, 99.9);
    expect(over?.status).toBe("breached");
    expect(over?.remainingSeconds).toBe(-408);
    expect(over?.usedPct).toBeGreaterThan(100);
  });

  it("scales the budget with the monitored time, not a fixed month", () => {
    // 1 hour observed at 99.9% -> 3.6 s allowed
    expect(computeErrorBudget(3600, 0, 99.9)?.allowedSeconds).toBe(3.6);
    expect(computeErrorBudget(3600, 30, 99.9)?.status).toBe("breached");
  });

  it("treats any downtime as a breach for a 100% SLA", () => {
    expect(computeErrorBudget(3600, 0, 100)?.status).toBe("ok");
    expect(computeErrorBudget(3600, 1, 100)?.status).toBe("breached");
  });

  it("returns null when there is nothing to compute", () => {
    expect(computeErrorBudget(0, 0, 99.9)).toBeNull();
    expect(computeErrorBudget(Number.NaN, 0, 99.9)).toBeNull();
    expect(computeErrorBudget(3600, 0, 0)).toBeNull();
    expect(computeErrorBudget(3600, 0, 101)).toBeNull();
  });

  it("ignores negative downtime", () => {
    expect(computeErrorBudget(3600, -5, 99.9)?.usedSeconds).toBe(0);
  });
});

describe("allowedDowntimeSeconds", () => {
  it("matches the usual SLA table for a 30-day month", () => {
    expect(allowedDowntimeSeconds(99.9)).toBe(2592); // 43m 12s
    expect(allowedDowntimeSeconds(99.99)).toBe(259.2); // 4m 19s
    expect(allowedDowntimeSeconds(99)).toBe(25920); // 7h 12m
  });
});

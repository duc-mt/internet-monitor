import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorBudgetCard } from "../src/components/ErrorBudgetCard";
import type { StatisticsResponse } from "../src/types";

const MONTH = 30 * 86400;

function makeStats(overrides: Partial<StatisticsResponse> = {}): StatisticsResponse {
  return {
    range_start: "2026-01-01T00:00:00+00:00",
    range_end: "2026-01-31T00:00:00+00:00",
    target_id: null,
    sample_count: 1000,
    avg_latency_ms: 20,
    min_latency_ms: 10,
    max_latency_ms: 40,
    median_latency_ms: 20,
    p95_latency_ms: 35,
    packet_loss_pct: 0,
    avg_jitter_ms: 1,
    uptime_pct: 99.99,
    outage_count: 0,
    longest_outage_seconds: null,
    monitoring_duration_seconds: MONTH,
    downtime_seconds: 0,
    effective_monitored_seconds: MONTH,
    ...overrides,
  };
}

describe("ErrorBudgetCard", () => {
  it("renders nothing until both the statistics and the SLA target are known", () => {
    const { container, rerender } = render(<ErrorBudgetCard stats={null} slaTargetPct={99.9} periodLabel="Last 30 days" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ErrorBudgetCard stats={makeStats()} slaTargetPct={null} periodLabel="Last 30 days" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows allowed, used and remaining downtime while within the SLA", () => {
    render(<ErrorBudgetCard stats={makeStats({ downtime_seconds: 300 })} slaTargetPct={99.9} periodLabel="Last 30 days" />);
    expect(screen.getByText("WITHIN SLA")).toBeInTheDocument();
    expect(screen.getByText("43m 12s")).toBeInTheDocument(); // allowed
    expect(screen.getByText("5m 0s")).toBeInTheDocument(); // used
    expect(screen.getByText("38m 12s")).toBeInTheDocument(); // remaining
    expect(screen.getByText("Remaining")).toBeInTheDocument();
  });

  it("flags an at-risk budget", () => {
    render(<ErrorBudgetCard stats={makeStats({ downtime_seconds: 2200 })} slaTargetPct={99.9} periodLabel="Last 30 days" />);
    expect(screen.getByText("AT RISK")).toBeInTheDocument();
  });

  it("flags a breach and reports how far over budget the connection is", () => {
    render(<ErrorBudgetCard stats={makeStats({ downtime_seconds: 3000 })} slaTargetPct={99.9} periodLabel="Last 30 days" />);
    expect(screen.getByText("SLA BREACHED")).toBeInTheDocument();
    expect(screen.getByText("Over by")).toBeInTheDocument();
    expect(screen.getByText("6m 48s")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });

  it("explains when there is not enough data to compute a budget", () => {
    render(
      <ErrorBudgetCard stats={makeStats({ effective_monitored_seconds: 0 })} slaTargetPct={99.9} periodLabel="Last hour" />
    );
    expect(screen.getByText(/not enough monitoring data/i)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

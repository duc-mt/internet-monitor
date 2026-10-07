import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { HoverTooltip } from "../src/components/HoverTooltip";
import { buildSeries } from "../src/services/chartData";
import type { Measurement, Target } from "../src/types";

const T0 = Date.parse("2026-01-01T12:00:00Z");
const targets = [
  { id: 1, name: "Gateway", host: "192.168.1.1" },
  { id: 2, name: "Cloudflare DNS", host: "1.1.1.1" },
] as Target[];

const ms = (id: number, target_id: number, latency: number | null, loss: number, jitter: number | null): Measurement => ({
  id, target_id, timestamp: new Date(T0).toISOString(), latency_ms: latency, packet_loss: loss, jitter_ms: jitter,
  success: loss < 100, error: null,
});

const series = buildSeries([ms(1, 1, 2.5, 0, 0.4), ms(2, 2, null, 100, null)], targets);
const colors = ["#34d8c6", "#7c9eff"];

describe("HoverTooltip", () => {
  it("renders nothing when inactive or without a numeric time", () => {
    const { container, rerender } = render(<HoverTooltip active={false} label={T0} series={series} targets={targets} colors={colors} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<HoverTooltip active label="x" series={series} targets={targets} colors={colors} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows latency, jitter and packet loss for every target at the hovered time", () => {
    render(<HoverTooltip active label={T0} series={series} targets={targets} colors={colors} />);
    expect(screen.getByText("Gateway")).toBeInTheDocument();
    expect(screen.getByText("Cloudflare DNS")).toBeInTheDocument();
    expect(screen.getByText("2.50 ms")).toBeInTheDocument(); // gateway latency
    expect(screen.getByText("0.40 ms")).toBeInTheDocument(); // gateway jitter
    expect(screen.getAllByText("Packet loss")).toHaveLength(2);
  });

  it("marks a lost check as no response with 100% packet loss", () => {
    render(<HoverTooltip active label={T0} series={series} targets={targets} colors={colors} />);
    expect(screen.getByText("no response")).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
  });

  it("skips targets that have no sample near the hovered time", () => {
    render(<HoverTooltip active label={T0 + 3_600_000} series={series} targets={targets} colors={colors} />);
    expect(screen.queryByText("Gateway")).not.toBeInTheDocument();
  });
});

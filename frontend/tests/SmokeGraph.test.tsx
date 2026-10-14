import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SmokeGraph, SmokeTooltip, SMOKE_RANGE_OPTIONS } from "../src/components/SmokeGraph";
import type { Measurement, Target } from "../src/types";

const targets: Target[] = [
  { id: 1, name: "Gateway", host: "192.168.1.1", protocol: "icmp", port: null, is_gateway: true, enabled: true, interval_seconds: 60, created_at: "" },
  { id: 2, name: "Cloudflare", host: "1.1.1.1", protocol: "icmp", port: null, is_gateway: false, enabled: true, interval_seconds: 60, created_at: "" },
];

// jsdom has no ResizeObserver, which Recharts' ResponsiveContainer needs to mount. (It then measures a 0x0 box and
// draws no SVG, so these tests cover the component's controls, legend and empty state, not the plotted shapes;
// the data that feeds the plot is tested in smokeData.test.ts.)
beforeAll(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

function row(minutesAgo: number, target_id = 2): Measurement {
  return {
    id: minutesAgo, target_id, timestamp: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    latency_ms: 20, packet_loss: 0, jitter_ms: 1, success: true, error: null,
    median_ms: 20, p25_ms: 18, p75_ms: 23, p95_ms: 40, min_ms: 15, max_ms: 55, iqr_ms: 5, jitter_rfc3550: 0.8, packet_count: 15,
  };
}

function renderGraph(over: Partial<React.ComponentProps<typeof SmokeGraph>> = {}) {
  const props = {
    measurements: [row(5), row(4), row(3)],
    targets,
    targetId: 2,
    onTargetChange: vi.fn(),
    rangeMinutes: 60,
    onRangeChange: vi.fn(),
    ...over,
  };
  render(<SmokeGraph {...props} />);
  return props;
}

describe("SmokeGraph", () => {
  it("offers the five smoke ranges: 5m, 15m, 1h, 6h, 24h", () => {
    expect(SMOKE_RANGE_OPTIONS.map((o) => o.label)).toEqual(["5m", "15m", "1h", "6h", "24h"]);
    renderGraph();
    for (const label of ["5m", "15m", "1h", "6h", "24h"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("marks the active range and reports a range change", () => {
    const props = renderGraph({ rangeMinutes: 60 });
    expect(screen.getByRole("button", { name: "1h" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "6h" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "6h" }));
    expect(props.onRangeChange).toHaveBeenCalledWith(360);
  });

  it("lets the user switch target", () => {
    const props = renderGraph();
    const select = screen.getByLabelText("Target") as HTMLSelectElement;
    expect(select.value).toBe("2");
    fireEvent.change(select, { target: { value: "1" } });
    expect(props.onTargetChange).toHaveBeenCalledWith(1);
  });

  it("explains the three layers in a legend", () => {
    renderGraph();
    const legend = screen.getByRole("list", { name: /chart legend/i });
    expect(legend).toHaveTextContent("Median");
    expect(legend).toHaveTextContent("IQR p25–p75");
    expect(legend).toHaveTextContent("Tail min–p95");
    expect(legend).toHaveTextContent("Packet loss");
  });

  it("toggles the loss layer", () => {
    renderGraph();
    const toggle = screen.getByRole("button", { name: /loss/i });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("list", { name: /chart legend/i })).not.toHaveTextContent("Packet loss");
  });

  it("shows an empty state, and disables the PNG export, when the target has no data in the window", () => {
    renderGraph({ measurements: [row(5, 1)] }); // only another target's data
    expect(screen.getByText(/no measurements in this window yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save chart as png/i })).toBeDisabled();
  });

  it("enables the PNG export once there is data", () => {
    renderGraph();
    expect(screen.getByRole("button", { name: /save chart as png/i })).toBeEnabled();
  });
});

describe("SmokeTooltip", () => {
  const point = {
    ts: Date.parse("2026-10-14T10:00:00Z"), median: 20, iqr: [18, 23] as [number, number], tail: [15, 40] as [number, number],
    iqrMs: 5, p95: 40, min: 15, max: 55, jitter: 0.8, loss: 6.67, samples: 1,
  };

  it("lists median, IQR, p95, min/max, jitter and loss for the hovered burst", () => {
    render(<SmokeTooltip active payload={[{ payload: point }]} />);
    expect(screen.getByText("Median").nextSibling).toHaveTextContent("20.0 ms");
    expect(screen.getByText("IQR").nextSibling).toHaveTextContent("5.0 ms");
    expect(screen.getByText("p95").nextSibling).toHaveTextContent("40.0 ms");
    expect(screen.getByText("Min / Max").nextSibling).toHaveTextContent("15.0 ms / 55.0 ms");
    expect(screen.getByText("Jitter").nextSibling).toHaveTextContent("0.80 ms");
    expect(screen.getByText("Loss").nextSibling).toHaveTextContent("6.7%");
  });

  it("says how many checks a thinned point stands for", () => {
    render(<SmokeTooltip active payload={[{ payload: { ...point, samples: 60 } }]} />);
    expect(screen.getByText(/60 checks/)).toBeInTheDocument();
  });

  it("renders nothing when inactive", () => {
    const { container } = render(<SmokeTooltip active={false} payload={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

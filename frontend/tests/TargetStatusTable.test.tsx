import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TargetStatusTable } from "../src/components/TargetStatusTable";
import type { TargetStatus } from "../src/types";

const sample: TargetStatus[] = [
  { target_id: 1, name: "Gateway", host: "192.168.1.1", reachable: true, latency_ms: 1.2, packet_loss: 0, last_checked: new Date().toISOString() },
  { target_id: 2, name: "Cloudflare DNS", host: "1.1.1.1", reachable: false, latency_ms: null, packet_loss: 100, last_checked: new Date().toISOString() },
];

describe("TargetStatusTable", () => {
  it("shows an empty state when there are no targets", () => {
    render(<TargetStatusTable targets={[]} />);
    expect(screen.getByText(/no targets configured/i)).toBeInTheDocument();
  });

  it("renders a row per target with host and latency", () => {
    render(<TargetStatusTable targets={sample} />);
    expect(screen.getByText("Gateway")).toBeInTheDocument();
    expect(screen.getByText("Cloudflare DNS")).toBeInTheDocument();
    expect(screen.getByText("192.168.1.1")).toBeInTheDocument();
    expect(screen.getByText("1.20 ms")).toBeInTheDocument();
  });

  it("shows the burst median and IQR, falling back to latency for rows without them", () => {
    render(
      <TargetStatusTable
        targets={[
          { ...sample[0], median_ms: 3.45, iqr_ms: 0.6 },
          { target_id: 3, name: "Legacy", host: "9.9.9.9", reachable: true, latency_ms: 40, packet_loss: 0, last_checked: new Date().toISOString() },
        ]}
      />
    );
    expect(screen.getByRole("columnheader", { name: "Median" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "IQR" })).toBeInTheDocument();
    expect(screen.getByText("3.45 ms")).toBeInTheDocument();
    expect(screen.getByText("0.60 ms")).toBeInTheDocument();
    expect(screen.getByText("40.0 ms")).toBeInTheDocument();
  });

  it("offers a traceroute action per row only when a handler is provided", () => {
    const { rerender } = render(<TargetStatusTable targets={sample} />);
    expect(screen.queryByRole("button", { name: /traceroute to/i })).not.toBeInTheDocument();

    const onTrace = vi.fn();
    rerender(<TargetStatusTable targets={sample} onTrace={onTrace} />);
    fireEvent.click(screen.getByRole("button", { name: "Traceroute to Cloudflare DNS" }));
    expect(onTrace).toHaveBeenCalledWith(sample[1]);
  });

  it("renders a dash for unreachable targets with no latency", () => {
    render(<TargetStatusTable targets={sample} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });
});

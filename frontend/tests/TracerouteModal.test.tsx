import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TracerouteModal } from "../src/components/TracerouteModal";
import { ApiError } from "../src/services/api";
import type { TracerouteResult } from "../src/types";

const runTraceroute = vi.fn();

vi.mock("../src/services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/services/api")>();
  return { ...actual, api: { ...actual.api, runTraceroute: (id: number) => runTraceroute(id) } };
});

// Dummy data only: RFC 1918 / RFC 6598 ranges and a public DNS resolver.
const RESULT: TracerouteResult = {
  target_id: 2,
  target_name: "Cloudflare DNS",
  host: "1.1.1.1",
  timed_out: false,
  elapsed_seconds: 4.2,
  raw: "traceroute to 1.1.1.1 (1.1.1.1), 15 hops max",
  hops: [
    { hop: 1, address: "192.168.1.1", rtts_ms: [0.5, 0.6, 0.4], avg_ms: 0.5, loss_pct: 0, scope: "private", extra_addresses: [] },
    { hop: 2, address: null, rtts_ms: [null, null, null], avg_ms: null, loss_pct: 100, scope: "unknown", extra_addresses: [] },
    { hop: 3, address: "100.64.0.1", rtts_ms: [5.1, 5.3, null], avg_ms: 5.2, loss_pct: 33.3, scope: "cgnat", extra_addresses: [] },
    { hop: 4, address: "1.1.1.1", rtts_ms: [9.8, 9.9, 10.1], avg_ms: 9.93, loss_pct: 0, scope: "public", extra_addresses: [] },
  ],
};

const target = { id: 2, name: "Cloudflare DNS", host: "1.1.1.1" };

describe("TracerouteModal", () => {
  beforeEach(() => runTraceroute.mockReset());

  it("shows a loading state, then one row per hop with its network segment", async () => {
    runTraceroute.mockResolvedValue(RESULT);
    render(<TracerouteModal target={target} onClose={() => {}} />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("192.168.1.1")).toBeInTheDocument();
    expect(runTraceroute).toHaveBeenCalledWith(2);
    expect(screen.getByText("100.64.0.1")).toBeInTheDocument();
    expect(screen.getByText("LAN")).toBeInTheDocument();
    expect(screen.getByText("ISP · CGNAT")).toBeInTheDocument();
    expect(screen.getByText("Internet")).toBeInTheDocument();
  });

  it("explains that a silent hop is not necessarily a fault", async () => {
    runTraceroute.mockResolvedValue(RESULT);
    render(<TracerouteModal target={target} onClose={() => {}} />);
    expect(await screen.findByText(/often a router that ignores ICMP/i)).toBeInTheDocument();
  });

  it("switches to the raw output in a monospace block", async () => {
    runTraceroute.mockResolvedValue(RESULT);
    render(<TracerouteModal target={target} onClose={() => {}} />);
    await screen.findByText("192.168.1.1");

    fireEvent.click(screen.getByRole("button", { name: "Raw output" }));
    const pre = screen.getByText(/traceroute to 1\.1\.1\.1/);
    expect(pre.tagName).toBe("PRE");
    expect(pre.className).toContain("font-mono");
  });

  it("flags a partial result when the time budget ran out", async () => {
    runTraceroute.mockResolvedValue({ ...RESULT, timed_out: true });
    render(<TracerouteModal target={target} onClose={() => {}} />);
    expect(await screen.findByText(/time budget exceeded/i)).toBeInTheDocument();
  });

  it("shows the API error without the JSON quotes", async () => {
    runTraceroute.mockRejectedValue(new ApiError(503, '"traceroute is not installed on this system"'));
    render(<TracerouteModal target={target} onClose={() => {}} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("traceroute is not installed on this system");
    expect(alert.textContent).not.toContain('"');
  });

  it("runs the trace again on request", async () => {
    runTraceroute.mockResolvedValue(RESULT);
    render(<TracerouteModal target={target} onClose={() => {}} />);
    await screen.findByText("192.168.1.1");

    fireEvent.click(screen.getByRole("button", { name: "Run again" }));
    await screen.findByText("192.168.1.1");
    expect(runTraceroute).toHaveBeenCalledTimes(2);
  });
});

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Dashboard } from "../src/pages/Dashboard";
import { ThemeProvider } from "../src/hooks/useTheme";
import { api } from "../src/services/api";
import type { AppSettings, StatisticsResponse, StatusResponse, Target } from "../src/types";

vi.mock("../src/services/api", () => ({
  api: {
    getStatus: vi.fn(),
    listTargets: vi.fn(),
    listMeasurements: vi.fn(),
    listOutages: vi.fn(),
    getStatistics: vi.fn(),
    getSettings: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

const mockStatus: StatusResponse = {
  online: true,
  quality: "good",
  latency_ms: 24.5,
  packet_loss: 0,
  jitter_ms: 1.2,
  monitoring_uptime_seconds: 3661,
  uptime_pct_24h: 99.8,
  targets_reachable: 3,
  targets_total: 3,
  targets: [
    { target_id: 1, name: "Gateway", host: "192.168.1.1", reachable: true, latency_ms: 1.1, packet_loss: 0, last_checked: new Date().toISOString() },
  ],
  active_outage: false,
  monitoring_running: true,
};

const mockTargets: Target[] = [
  { id: 1, name: "Gateway", host: "192.168.1.1", protocol: "icmp", port: null, is_gateway: true, enabled: true, interval_seconds: 60, created_at: "2026-01-01T00:00:00Z" },
  { id: 2, name: "Cloudflare", host: "1.1.1.1", protocol: "icmp", port: null, is_gateway: false, enabled: true, interval_seconds: 60, created_at: "2026-01-01T00:00:00Z" },
];

const burstStatus: StatusResponse = {
  ...mockStatus,
  median_ms: 23.4,
  iqr_ms: 3.2,
  p95_ms: 41.7,
  jitter_rfc3550_ms: 1.05,
  stability: "excellent",
};

const mockMonthStats = {
  uptime_pct: 99.98,
  downtime_seconds: 300,
  effective_monitored_seconds: 30 * 86400,
} as StatisticsResponse;

const mockSettings = { sla_target_pct: 99.9 } as AppSettings;

function renderDashboard() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </ThemeProvider>
  );
}

describe("Dashboard", () => {
  beforeEach(() => {
    vi.mocked(api.getStatus).mockResolvedValue(mockStatus);
    vi.mocked(api.listTargets).mockResolvedValue(mockTargets);
    vi.mocked(api.listMeasurements).mockResolvedValue([]);
    vi.mocked(api.listOutages).mockResolvedValue([]);
    vi.mocked(api.getStatistics).mockResolvedValue(mockMonthStats);
    vi.mocked(api.getSettings).mockResolvedValue(mockSettings);
  });

  it("shows a loading state before data arrives", async () => {
    let resolveStatus!: (value: StatusResponse) => void;
    vi.mocked(api.getStatus).mockReturnValue(
      new Promise((resolve) => {
        resolveStatus = resolve;
      })
    );
    renderDashboard();
    expect(screen.getByText(/connecting/i)).toBeInTheDocument();
    resolveStatus(mockStatus);
    await waitFor(() => expect(screen.queryByText(/connecting/i)).not.toBeInTheDocument());
  });

  it("renders status once loaded", async () => {
    renderDashboard();
    await waitFor(() => expect(screen.getAllByText("Online")[0]).toBeInTheDocument());
    expect(screen.getByText(/3 of 3 targets reachable/i)).toBeInTheDocument();
    expect(screen.getByText("Good")).toBeInTheDocument();
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.mocked(api.getStatus).mockRejectedValue(new Error("Could not reach the Internet Monitor backend."));
    renderDashboard();
    await waitFor(() => expect(screen.getByText(/could not reach/i)).toBeInTheDocument());
  });

  it("shows the SLA error budget for the last 30 days", async () => {
    renderDashboard();
    await waitFor(() => expect(screen.getByText("WITHIN SLA")).toBeInTheDocument());
    expect(api.getStatistics).toHaveBeenCalledWith({ range: "30d" });
    expect(screen.getByText("43m 12s")).toBeInTheDocument();
  });

  it("shows the burst figures: base latency, IQR, RFC 3550 jitter, p95 and the stability score", async () => {
    vi.mocked(api.getStatus).mockResolvedValue(burstStatus);
    renderDashboard();
    await waitFor(() => expect(screen.getByText("Base latency")).toBeInTheDocument());
    expect(screen.getByText("23.4")).toBeInTheDocument();
    expect(screen.getByText("IQR (variation)")).toBeInTheDocument();
    expect(screen.getByText("3.20")).toBeInTheDocument();
    expect(screen.getByText("Jitter (RFC 3550)")).toBeInTheDocument();
    expect(screen.getByText("1.05")).toBeInTheDocument();
    expect(screen.getByText("Tail latency (p95)")).toBeInTheDocument();
    expect(screen.getByText("41.7")).toBeInTheDocument();
    expect(screen.getByText("Stability score")).toBeInTheDocument();
    expect(screen.getByText("EXCELLENT")).toBeInTheDocument();
  });

  it("falls back to the older latency/jitter fields when the server sends no burst figures", async () => {
    renderDashboard();
    await waitFor(() => expect(screen.getByText("Base latency")).toBeInTheDocument());
    expect(screen.getByText("24.5")).toBeInTheDocument(); // latency_ms
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument(); // no stability on an older server
  });

  it("draws the smoke graph for the first non-gateway target, over the last hour by default", async () => {
    renderDashboard();
    await waitFor(() => expect(screen.getByLabelText("Target")).toBeInTheDocument());
    expect((screen.getByLabelText("Target") as HTMLSelectElement).value).toBe("2");
    expect(screen.getByRole("button", { name: "1h" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(api.listMeasurements).toHaveBeenCalledWith(expect.objectContaining({ target_id: 2, limit: 20000 })));
  });

  it("flags an active outage in the subheading", async () => {
    vi.mocked(api.getStatus).mockResolvedValue({ ...mockStatus, active_outage: true });
    renderDashboard();
    await waitFor(() => expect(screen.getByText(/outage in progress/i)).toBeInTheDocument());
  });
});

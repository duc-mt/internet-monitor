import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Dashboard } from "../src/pages/Dashboard";
import { ThemeProvider } from "../src/hooks/useTheme";
import { api } from "../src/services/api";
import type { StatusResponse, Target } from "../src/types";

vi.mock("../src/services/api", () => ({
  api: {
    getStatus: vi.fn(),
    listTargets: vi.fn(),
    listMeasurements: vi.fn(),
    listOutages: vi.fn(),
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
  targets_reachable: 3,
  targets_total: 3,
  targets: [
    { target_id: 1, name: "Gateway", host: "192.168.1.1", reachable: true, latency_ms: 1.1, packet_loss: 0, last_checked: new Date().toISOString() },
  ],
  active_outage: false,
  monitoring_running: true,
};

const mockTargets: Target[] = [
  { id: 1, name: "Gateway", host: "192.168.1.1", protocol: "icmp", port: null, is_gateway: true, enabled: true, interval_seconds: 5, created_at: "2026-01-01T00:00:00Z" },
];

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
  });

  it("shows a loading state before data arrives", () => {
    renderDashboard();
    expect(screen.getByText(/connecting/i)).toBeInTheDocument();
  });

  it("renders status once loaded", async () => {
    renderDashboard();
    await waitFor(() => expect(screen.getByText("Online")).toBeInTheDocument());
    expect(screen.getByText(/3 of 3 targets reachable/i)).toBeInTheDocument();
    expect(screen.getByText("Good")).toBeInTheDocument();
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.mocked(api.getStatus).mockRejectedValue(new Error("Could not reach the Internet Monitor backend."));
    renderDashboard();
    await waitFor(() => expect(screen.getByText(/could not reach/i)).toBeInTheDocument());
  });

  it("flags an active outage in the subheading", async () => {
    vi.mocked(api.getStatus).mockResolvedValue({ ...mockStatus, active_outage: true });
    renderDashboard();
    await waitFor(() => expect(screen.getByText(/outage in progress/i)).toBeInTheDocument());
  });
});

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { OutageList } from "../src/components/OutageList";
import type { Outage } from "../src/types";

describe("OutageList", () => {
  it("shows an empty state with no outages", () => {
    render(<OutageList outages={[]} />);
    expect(screen.getByText(/no outages recorded/i)).toBeInTheDocument();
  });

  it("marks an active outage as ongoing rather than showing a duration", () => {
    const active: Outage = {
      id: 1, started_at: new Date().toISOString(), ended_at: null, duration_seconds: null,
      reason: "all targets down", affected_targets: ["Cloudflare DNS", "Google DNS"],
      failed_checks: 3, is_active: true,
    };
    render(<OutageList outages={[active]} />);
    expect(screen.getByText("ongoing")).toBeInTheDocument();
    expect(screen.getByText("Cloudflare DNS, Google DNS")).toBeInTheDocument();
  });

  it("limits to 5 rows when compact", () => {
    const outages: Outage[] = Array.from({ length: 8 }, (_, i) => ({
      id: i, started_at: new Date().toISOString(), ended_at: new Date().toISOString(),
      duration_seconds: 60, reason: "test", affected_targets: [], failed_checks: 3, is_active: false,
    }));
    render(<OutageList outages={outages} compact />);
    expect(screen.getAllByText("1m 0s")).toHaveLength(5);
  });
});

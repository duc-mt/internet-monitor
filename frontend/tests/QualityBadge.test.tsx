import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QualityBadge } from "../src/components/QualityBadge";

describe("QualityBadge", () => {
  it.each([
    ["excellent", "Excellent"],
    ["good", "Good"],
    ["fair", "Fair"],
    ["poor", "Poor"],
    ["offline", "Offline"],
    ["unknown", "Unknown"],
  ] as const)("renders the %s label", (quality, label) => {
    render(<QualityBadge quality={quality} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

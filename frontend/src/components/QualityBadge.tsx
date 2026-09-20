import type { Quality } from "../types";

export const QUALITY_COLOR: Record<Quality, string> = {
  excellent: "var(--color-healthy)",
  good: "var(--color-healthy)",
  fair: "var(--color-degraded)",
  poor: "var(--color-offline)",
  offline: "var(--color-offline)",
  unknown: "var(--color-unknown)",
};

export const QUALITY_LABEL: Record<Quality, string> = {
  excellent: "Excellent",
  good: "Good",
  fair: "Fair",
  poor: "Poor",
  offline: "Offline",
  unknown: "Unknown",
};

export function QualityBadge({ quality }: { quality: Quality }) {
  const color = QUALITY_COLOR[quality];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
      style={{ borderColor: color, color }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {QUALITY_LABEL[quality]}
    </span>
  );
}

export function StatusDot({ ok, size = "sm" }: { ok: boolean | null; size?: "sm" | "md" }) {
  const color = ok === null ? "var(--color-unknown)" : ok ? "var(--color-healthy)" : "var(--color-offline)";
  const dim = size === "sm" ? "h-2 w-2" : "h-2.5 w-2.5";
  return <span className={`inline-block rounded-full ${dim}`} style={{ backgroundColor: color }} />;
}

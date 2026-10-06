export type BudgetStatus = "ok" | "warning" | "breached";

export interface ErrorBudget {
  /** Downtime the SLA tolerates over the monitored period. */
  allowedSeconds: number;
  usedSeconds: number;
  /** Negative once the SLA is breached. */
  remainingSeconds: number;
  /** Share of the budget consumed, 0-100+ (it can exceed 100). */
  usedPct: number;
  status: BudgetStatus;
}

/** Budget usage at which the card turns amber, before the SLA is actually breached. */
export const WARNING_AT_PCT = 80;

const round2 = (n: number) => Math.round(n * 100) / 100;

/**
 * Error budget = monitored time x (1 - SLA/100). `monitoredSeconds` should be
 * the time actually observed (sleep gaps excluded) - the same denominator the
 * backend uses for uptime% - not the wall-clock size of the selected range.
 * Returns null when there is nothing meaningful to compute.
 */
export function computeErrorBudget(
  monitoredSeconds: number,
  downtimeSeconds: number,
  slaTargetPct: number
): ErrorBudget | null {
  if (!Number.isFinite(monitoredSeconds) || monitoredSeconds <= 0) return null;
  if (!Number.isFinite(slaTargetPct) || slaTargetPct <= 0 || slaTargetPct > 100) return null;

  const used = Math.max(0, downtimeSeconds);
  // Rounded so float noise (99.9 is not exact) can't turn 43m 12s into 43m 11s.
  const allowed = round2(monitoredSeconds * (1 - slaTargetPct / 100));
  const usedPct = allowed > 0 ? (used / allowed) * 100 : used > 0 ? 100 : 0;

  const status: BudgetStatus = used > allowed ? "breached" : usedPct >= WARNING_AT_PCT ? "warning" : "ok";
  return { allowedSeconds: allowed, usedSeconds: used, remainingSeconds: allowed - used, usedPct, status };
}

/** Downtime an SLA allows over a period of `days`, e.g. 99.9% over 30 days = 43m 12s. */
export function allowedDowntimeSeconds(slaTargetPct: number, days = 30): number {
  return round2(days * 86400 * (1 - slaTargetPct / 100));
}

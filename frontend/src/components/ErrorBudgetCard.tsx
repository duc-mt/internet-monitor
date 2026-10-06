import { ShieldAlert, ShieldCheck } from "lucide-react";
import { computeErrorBudget, type BudgetStatus } from "../services/sla";
import { formatDuration } from "../services/format";
import type { StatisticsResponse } from "../types";

const STATUS_STYLE: Record<BudgetStatus, { label: string; text: string; badge: string; bar: string }> = {
  ok: {
    label: "WITHIN SLA",
    text: "text-healthy",
    badge: "text-healthy bg-healthy-soft",
    bar: "from-emerald-500 to-teal-400",
  },
  warning: {
    label: "AT RISK",
    text: "text-degraded",
    badge: "text-degraded bg-degraded-soft",
    bar: "from-amber-500 to-orange-400",
  },
  breached: {
    label: "SLA BREACHED",
    text: "text-offline",
    badge: "text-offline bg-offline-soft",
    bar: "from-rose-500 to-red-500",
  },
};

function Metric({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest font-semibold text-muted">{label}</p>
      <p className={`mt-1 font-mono font-bold font-tabular text-lg ${valueClass ?? "text-text"}`}>{value}</p>
    </div>
  );
}

/**
 * How much of the SLA's allowed downtime has been used over `periodLabel`.
 * Renders nothing until both the statistics and the SLA target are known.
 */
export function ErrorBudgetCard({
  stats,
  slaTargetPct,
  periodLabel,
}: {
  stats: StatisticsResponse | null;
  slaTargetPct: number | null;
  periodLabel: string;
}) {
  if (stats === null || slaTargetPct === null) return null;

  const budget = computeErrorBudget(stats.effective_monitored_seconds, stats.downtime_seconds, slaTargetPct);

  return (
    <div className="rounded-card border border-border bg-panel p-5 shadow-sm transition-all-fast">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold tracking-tight text-text">SLA error budget · Ngân sách lỗi</h3>
          <p className="text-xs text-muted font-medium mt-0.5">
            <span className="font-mono">{slaTargetPct}%</span> target · {periodLabel}
          </p>
        </div>
        {budget && (
          <span
            className={`flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-widest rounded-full px-3 py-1 ${STATUS_STYLE[budget.status].badge}`}
          >
            {budget.status === "ok" ? <ShieldCheck size={12} /> : <ShieldAlert size={12} />}
            {STATUS_STYLE[budget.status].label}
          </span>
        )}
      </div>

      {budget === null ? (
        <p className="mt-4 text-sm text-muted">
          Not enough monitoring data yet · Chưa đủ dữ liệu để tính ngân sách lỗi.
        </p>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-3 gap-4">
            <Metric label="Allowed" value={formatDuration(budget.allowedSeconds)} />
            <Metric label="Used" value={formatDuration(budget.usedSeconds)} valueClass={STATUS_STYLE[budget.status].text} />
            <Metric
              label={budget.remainingSeconds >= 0 ? "Remaining" : "Over by"}
              value={formatDuration(Math.abs(budget.remainingSeconds))}
              valueClass={budget.remainingSeconds < 0 ? STATUS_STYLE.breached.text : undefined}
            />
          </div>

          <div
            className="mt-4 h-2 rounded-full bg-panel-alt overflow-hidden"
            role="progressbar"
            aria-label="Error budget used"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.min(100, Math.round(budget.usedPct))}
          >
            <div
              className={`h-full rounded-full bg-gradient-to-r ${STATUS_STYLE[budget.status].bar} transition-all-fast`}
              style={{ width: `${Math.min(100, budget.usedPct)}%` }}
            />
          </div>

          <p className="mt-3 text-xs text-muted font-medium">
            <span className="font-mono">{budget.usedPct.toFixed(budget.usedPct < 10 ? 1 : 0)}%</span> of budget used · Observed uptime{" "}
            <span className="font-mono">{stats.uptime_pct !== null ? `${stats.uptime_pct.toFixed(2)}%` : "—"}</span> vs target{" "}
            <span className="font-mono">{slaTargetPct}%</span>
          </p>
        </>
      )}
    </div>
  );
}

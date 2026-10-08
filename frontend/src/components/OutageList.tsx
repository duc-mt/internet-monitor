import type { Outage } from "../types";
import { formatDuration, formatTimestamp } from "../services/format";
import { EmptyState } from "./States";

function isSleepGap(o: Outage): boolean {
  return o.reason === "system_sleep";
}

export function OutageList({ outages, compact = false }: { outages: Outage[]; compact?: boolean }) {
  if (outages.length === 0) {
    return <EmptyState title="No outages recorded" description="Nice and stable so far · Kết nối mạng ổn định, chưa ghi nhận gián đoạn." />;
  }

  const rows = compact ? outages.slice(0, 5) : outages;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] font-semibold tracking-wider text-slate-400 uppercase border-b border-border bg-slate-50/50 dark:bg-slate-900/50">
            <th className="py-2.5 px-3 rounded-tl-md">Type</th>
            <th className="py-2.5 pr-3">Started</th>
            <th className="py-2.5 pr-3">Duration</th>
            <th className="py-2.5 pr-3">Affected targets</th>
            <th className="py-2.5 pr-3 rounded-tr-md">Failed checks</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => {
            const sleepGap = isSleepGap(o);
            return (
              <tr key={o.id} className="border-b border-border last:border-0 hover:bg-panel-alt/50 transition-colors">
                <td className="py-2.5 px-3">
                  {sleepGap ? (
                    <span className="inline-flex items-center rounded-full bg-panel-alt border border-border text-muted font-mono font-medium text-[11px] px-2.5 py-0.5">
                      System sleep
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full border border-offline/40 bg-offline/10 text-offline font-mono font-medium text-[11px] px-2.5 py-0.5">
                      Outage
                    </span>
                  )}
                </td>
                <td className="py-2.5 pr-3 font-mono text-xs text-muted">{formatTimestamp(o.started_at)}</td>
                <td className="py-2.5 pr-3 font-mono font-tabular">
                  {o.is_active ? (
                    <span className="inline-flex items-center rounded-full border border-amber-500/40 bg-amber-500/10 text-amber-500 font-mono font-medium text-[11px] px-2.5 py-0.5 animate-pulse">
                      ongoing
                    </span>
                  ) : (
                    formatDuration(o.duration_seconds)
                  )}
                </td>
                <td className="py-2.5 pr-3 text-xs text-muted">
                  {sleepGap ? "—" : o.affected_targets.join(", ") || "—"}
                </td>
                <td className="py-2.5 pr-3 font-mono font-tabular">{sleepGap ? "—" : o.failed_checks}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

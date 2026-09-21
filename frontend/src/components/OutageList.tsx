import type { Outage } from "../types";
import { formatDuration, formatTimestamp } from "../services/format";
import { EmptyState } from "./States";

function isSleepGap(o: Outage): boolean {
  return o.reason === "system_sleep";
}

export function OutageList({ outages, compact = false }: { outages: Outage[]; compact?: boolean }) {
  if (outages.length === 0) {
    return <EmptyState title="No outages recorded" description="Nice and stable so far." />;
  }

  const rows = compact ? outages.slice(0, 5) : outages;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted uppercase tracking-wide border-b border-border">
            <th className="py-2 pr-3 font-medium">Type</th>
            <th className="py-2 pr-3 font-medium">Started</th>
            <th className="py-2 pr-3 font-medium">Duration</th>
            <th className="py-2 pr-3 font-medium">Affected targets</th>
            <th className="py-2 pr-3 font-medium">Failed checks</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => {
            const sleepGap = isSleepGap(o);
            return (
              <tr key={o.id} className="border-b border-border last:border-0">
                <td className="py-2.5 pr-3">
                  {sleepGap ? (
                    <span className="inline-flex items-center rounded-full bg-panel-alt text-muted text-[11px] px-2 py-0.5">
                      System sleep
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full border border-offline text-offline text-[11px] px-2 py-0.5">
                      Outage
                    </span>
                  )}
                </td>
                <td className="py-2.5 pr-3 font-mono text-xs">{formatTimestamp(o.started_at)}</td>
                <td className="py-2.5 pr-3 font-mono font-tabular">
                  {o.is_active ? (
                    <span className="text-offline font-medium">ongoing</span>
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

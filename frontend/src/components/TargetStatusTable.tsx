import { Route } from "lucide-react";
import type { TargetStatus } from "../types";
import { formatLatency, formatPct, formatClock } from "../services/format";
import { StatusDot } from "./QualityBadge";
import { EmptyState } from "./States";

export function TargetStatusTable({
  targets,
  onTrace,
}: {
  targets: TargetStatus[];
  /** When provided, each row gets a "Traceroute" action button. */
  onTrace?: (target: TargetStatus) => void;
}) {
  if (targets.length === 0) {
    return (
      <EmptyState
        title="No targets configured"
        description="Add a target on the Targets page to start monitoring · Thêm máy chủ đích tại trang Targets để bắt đầu giám sát."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] font-semibold tracking-wider text-slate-400 uppercase border-b border-border bg-slate-50/50 dark:bg-slate-900/50">
            <th className="py-2.5 px-3 rounded-tl-md">Target</th>
            <th className="py-2.5 pr-3">Host</th>
            <th className="py-2.5 pr-3">Latency</th>
            <th className="py-2.5 pr-3">Loss</th>
            <th className={`py-2.5 pr-3 ${onTrace ? "" : "rounded-tr-md"}`}>Last check</th>
            {onTrace && (
              <th className="py-2.5 pr-3 rounded-tr-md">
                <span className="sr-only">Actions</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {targets.map((t) => (
            <tr key={t.target_id} className="border-b border-border last:border-0 hover:bg-panel-alt/50 transition-colors">
              <td className="py-2.5 px-3">
                <div className="flex items-center gap-2">
                  <StatusDot ok={t.last_checked ? t.reachable : null} />
                  <span className="font-medium text-text">{t.name}</span>
                </div>
              </td>
              <td className="py-2.5 pr-3 font-mono text-xs text-muted">{t.host}</td>
              <td className="py-2.5 pr-3 font-mono font-tabular">{formatLatency(t.latency_ms)}</td>
              <td className="py-2.5 pr-3 font-mono font-tabular">{formatPct(t.packet_loss)}</td>
              <td className="py-2.5 pr-3 text-xs text-muted font-mono">{formatClock(t.last_checked)}</td>
              {onTrace && (
                <td className="py-2.5 pr-3 text-right">
                  <button
                    onClick={() => onTrace(t)}
                    className="p-1.5 rounded-control text-muted hover:text-accent hover:bg-panel-alt transition-all-fast"
                    aria-label={`Traceroute to ${t.name}`}
                    title="Traceroute"
                  >
                    <Route size={14} />
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

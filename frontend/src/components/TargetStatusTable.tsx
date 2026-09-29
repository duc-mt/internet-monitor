import type { TargetStatus } from "../types";
import { formatLatency, formatPct, formatClock } from "../services/format";
import { StatusDot } from "./QualityBadge";
import { EmptyState } from "./States";

export function TargetStatusTable({ targets }: { targets: TargetStatus[] }) {
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
          <tr className="text-left text-xs text-muted uppercase tracking-widest border-b border-border">
            <th className="py-2.5 pr-3 font-semibold">Target</th>
            <th className="py-2.5 pr-3 font-semibold">Host</th>
            <th className="py-2.5 pr-3 font-semibold">Latency</th>
            <th className="py-2.5 pr-3 font-semibold">Loss</th>
            <th className="py-2.5 pr-3 font-semibold">Last check</th>
          </tr>
        </thead>
        <tbody>
          {targets.map((t) => (
            <tr key={t.target_id} className="border-b border-border last:border-0 hover:bg-panel-alt/50 transition-colors">
              <td className="py-2.5 pr-3">
                <div className="flex items-center gap-2">
                  <StatusDot ok={t.last_checked ? t.reachable : null} />
                  <span className="font-medium text-text">{t.name}</span>
                </div>
              </td>
              <td className="py-2.5 pr-3 font-mono text-xs text-muted">{t.host}</td>
              <td className="py-2.5 pr-3 font-mono font-tabular">{formatLatency(t.latency_ms)}</td>
              <td className="py-2.5 pr-3 font-mono font-tabular">{formatPct(t.packet_loss)}</td>
              <td className="py-2.5 pr-3 text-xs text-muted font-mono">{formatClock(t.last_checked)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useCallback, useState } from "react";
import { Wifi, Gauge, PackageX, Waves, Clock, Router, ShieldCheck } from "lucide-react";
import { useStatus } from "../hooks/useStatus";
import { usePolling } from "../hooks/usePolling";
import { api } from "../services/api";
import { StatCard } from "../components/StatCard";
import { QualityBadge } from "../components/QualityBadge";
import { LatencyChart, type RangeMinutes } from "../components/LatencyChart";
import { SpeedtestButton } from "../components/SpeedtestButton";
import { TargetStatusTable } from "../components/TargetStatusTable";
import { TracerouteModal } from "../components/TracerouteModal";
import { OutageList } from "../components/OutageList";
import { LoadingState, ErrorState } from "../components/States";
import { formatDuration, formatLatency, formatPct } from "../services/format";
import { useTargets } from "../hooks/useTargets";
import type { TargetStatus } from "../types";

export function Dashboard() {
  const { data: status, error: statusError, loading: statusLoading, refetch: refetchStatus } = useStatus();
  const { targets } = useTargets();
  const [rangeMinutes, setRangeMinutes] = useState<RangeMinutes>(5);
  const [tracing, setTracing] = useState<TargetStatus | null>(null);

  const measurementsFetcher = useCallback(() => {
    const start = new Date(Date.now() - rangeMinutes * 60_000).toISOString();
    return api.listMeasurements({ start, limit: 5000 });
  }, [rangeMinutes]);
  const { data: measurements } = usePolling(measurementsFetcher, 5000, [rangeMinutes]);

  const outagesFetcher = useCallback(() => api.listOutages({ limit: 5 }), []);
  const { data: outages } = usePolling(outagesFetcher, 15000);

  if (statusLoading && !status) return <LoadingState label="Connecting to Internet Monitor…" />;
  if (statusError && !status) return <ErrorState message={statusError} onRetry={refetchStatus} />;
  if (!status) return null;

  const enabledTargets = targets.filter((t) => t.enabled);

  return (
    <div className="space-y-6">
      <header className="sticky top-0 z-10 -mx-6 lg:-mx-8 -mt-6 lg:-mt-8 mb-6 px-6 lg:px-8 py-4 backdrop-blur-md bg-slate-50/80 dark:bg-slate-900/80 border-b border-border flex items-center justify-between transition-all-fast">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-text">Dashboard</h1>
          <p className="text-xs text-muted font-medium mt-0.5">
            {status.targets_reachable} of {status.targets_total} targets reachable · Giám sát kết nối thời gian thực
            {status.active_outage && <span className="text-offline font-semibold"> · outage in progress (Đang gián đoạn)</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {status.network_name && (
            <span className="flex items-center gap-1.5 text-xs font-mono text-muted border border-border bg-panel-alt rounded-full px-3 py-1 shadow-sm">
              <Router size={12} />
              {status.network_name}
            </span>
          )}
          <QualityBadge quality={status.quality} />
        </div>
      </header>

      <SpeedtestButton />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Internet"
          value={status.online ? "Online" : "Offline"}
          accentColor={status.online ? "var(--color-healthy)" : "var(--color-offline)"}
          icon={<Wifi size={16} />}
          sublabel={`Uptime: ${formatDuration(status.monitoring_uptime_seconds)}`}
        />
        <StatCard label="Latency" value={formatLatency(status.latency_ms).replace(" ms", "")} unit="ms" icon={<Gauge size={16} />} />
        <StatCard label="Packet loss" value={formatPct(status.packet_loss).replace("%", "")} unit="%" icon={<PackageX size={16} />} />
        <StatCard label="Jitter" value={formatLatency(status.jitter_ms).replace(" ms", "")} unit="ms" icon={<Waves size={16} />} />
        <StatCard
          label="Uptime (24h)"
          value={status.uptime_pct_24h !== null ? status.uptime_pct_24h.toFixed(1) : "—"}
          unit={status.uptime_pct_24h !== null ? "%" : undefined}
          icon={<ShieldCheck size={16} />}
          accentColor={
            status.uptime_pct_24h !== null && status.uptime_pct_24h < 99 ? "var(--color-degraded)" : undefined
          }
        />
      </div>

      <LatencyChart
        measurements={measurements ?? []}
        targets={enabledTargets}
        rangeMinutes={rangeMinutes}
        onRangeChange={setRangeMinutes}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-card border border-border bg-panel p-5 shadow-sm transition-all-fast">
          <h3 className="text-sm font-semibold tracking-tight text-text mb-3">Target status · Trạng thái mục tiêu</h3>
          <TargetStatusTable targets={status.targets} onTrace={setTracing} />
        </div>
        <div className="rounded-card border border-border bg-panel p-5 shadow-sm transition-all-fast">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold tracking-tight text-text">Recent outages · Sự cố gần đây</h3>
            <Clock size={14} className="text-muted" />
          </div>
          <OutageList outages={outages ?? []} compact />
        </div>
      </div>

      {tracing && (
        <TracerouteModal
          target={{ id: tracing.target_id, name: tracing.name, host: tracing.host }}
          onClose={() => setTracing(null)}
        />
      )}
    </div>
  );
}

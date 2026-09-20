import { useCallback, useState } from "react";
import { Wifi, Gauge, PackageX, Waves, Clock, Router } from "lucide-react";
import { useStatus } from "../hooks/useStatus";
import { usePolling } from "../hooks/usePolling";
import { api } from "../services/api";
import { StatCard } from "../components/StatCard";
import { QualityBadge } from "../components/QualityBadge";
import { LatencyChart, type RangeMinutes } from "../components/LatencyChart";
import { TargetStatusTable } from "../components/TargetStatusTable";
import { OutageList } from "../components/OutageList";
import { LoadingState, ErrorState } from "../components/States";
import { formatDuration, formatLatency, formatPct } from "../services/format";
import { useTargets } from "../hooks/useTargets";

export function Dashboard() {
  const { data: status, error: statusError, loading: statusLoading, refetch: refetchStatus } = useStatus();
  const { targets } = useTargets();
  const [rangeMinutes, setRangeMinutes] = useState<RangeMinutes>(5);

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
    <div className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Dashboard</h1>
          <p className="text-sm text-muted mt-0.5">
            {status.targets_reachable} of {status.targets_total} targets reachable
            {status.active_outage && <span className="text-offline"> · outage in progress</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {status.network_name && (
            <span className="flex items-center gap-1.5 text-xs text-muted border border-border rounded-full px-2.5 py-1">
              <Router size={12} />
              {status.network_name}
            </span>
          )}
          <QualityBadge quality={status.quality} />
        </div>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Internet"
          value={status.online ? "Online" : "Offline"}
          accentColor={status.online ? "var(--color-healthy)" : "var(--color-offline)"}
          icon={<Wifi size={16} />}
          sublabel={`Monitoring uptime: ${formatDuration(status.monitoring_uptime_seconds)}`}
        />
        <StatCard label="Latency" value={formatLatency(status.latency_ms).replace(" ms", "")} unit="ms" icon={<Gauge size={16} />} />
        <StatCard label="Packet loss" value={formatPct(status.packet_loss).replace("%", "")} unit="%" icon={<PackageX size={16} />} />
        <StatCard label="Jitter" value={formatLatency(status.jitter_ms).replace(" ms", "")} unit="ms" icon={<Waves size={16} />} />
      </div>

      <LatencyChart
        measurements={measurements ?? []}
        targets={enabledTargets}
        rangeMinutes={rangeMinutes}
        onRangeChange={setRangeMinutes}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-card border border-border bg-panel p-4">
          <h3 className="text-sm font-medium mb-3">Target status</h3>
          <TargetStatusTable targets={status.targets} />
        </div>
        <div className="rounded-card border border-border bg-panel p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium">Recent outages</h3>
            <Clock size={14} className="text-muted" />
          </div>
          <OutageList outages={outages ?? []} compact />
        </div>
      </div>
    </div>
  );
}

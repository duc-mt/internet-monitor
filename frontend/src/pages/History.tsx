import { useCallback, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { api } from "../services/api";
import { usePolling } from "../hooks/usePolling";
import { useTargets } from "../hooks/useTargets";
import { LatencyChart } from "../components/LatencyChart";
import { OutageList } from "../components/OutageList";
import { LoadingState, ErrorState } from "../components/States";
import { formatDuration, formatLatency, formatPct } from "../services/format";
import type { RangeName } from "../types";

const RANGE_TABS: { label: string; value: RangeName }[] = [
  { label: "Last hour", value: "1h" },
  { label: "Last 24 hours", value: "24h" },
  { label: "Last 7 days", value: "7d" },
  { label: "Last 30 days", value: "30d" },
  { label: "Custom", value: "custom" },
];

const HISTORY_CHART_RANGES = [
  { label: "1h", minutes: 60 },
  { label: "24h", minutes: 1440 },
  { label: "7d", minutes: 10080 },
  { label: "30d", minutes: 43200 },
];

export function History() {
  const { targets } = useTargets();
  const [range, setRange] = useState<RangeName>("24h");
  const [targetId, setTargetId] = useState<number | undefined>(undefined);
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [chartMinutes, setChartMinutes] = useState(1440);

  const rangeParams = useMemo(() => {
    if (range === "custom") {
      if (!customStart || !customEnd) return null;
      return { start: new Date(customStart).toISOString(), end: new Date(customEnd).toISOString() };
    }
    return {};
  }, [range, customStart, customEnd]);

  const statsFetcher = useCallback(() => {
    if (rangeParams === null) return Promise.reject(new Error("Pick a custom start and end date."));
    return api.getStatistics({ range, target_id: targetId, ...rangeParams });
  }, [range, targetId, rangeParams]);
  const { data: stats, error: statsError, loading: statsLoading } = usePolling(statsFetcher, 30000, [range, targetId, rangeParams]);

  const measurementsFetcher = useCallback(() => {
    const start = new Date(Date.now() - chartMinutes * 60_000).toISOString();
    return api.listMeasurements({ target_id: targetId, start, limit: 5000 });
  }, [chartMinutes, targetId]);
  const { data: measurements } = usePolling(measurementsFetcher, 10000, [chartMinutes, targetId]);

  const outagesFetcher = useCallback(() => api.listOutages({ limit: 100 }), []);
  const { data: outages } = usePolling(outagesFetcher, 20000);

  const chartTargets = targetId ? targets.filter((t) => t.id === targetId) : targets.filter((t) => t.enabled);

  return (
    <div className="space-y-5">
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-lg font-semibold">History</h1>
          <p className="text-sm text-muted mt-0.5">Latency, packet loss, jitter, and outage history.</p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={api.exportMeasurementsCsvUrl({ target_id: targetId })}
            className="flex items-center gap-1.5 text-xs rounded-control border border-border px-2.5 py-1.5 text-muted hover:text-text hover:border-accent"
          >
            <Download size={13} /> CSV
          </a>
          <a
            href={api.exportReportJsonUrl({ range, target_id: targetId, ...(rangeParams ?? {}) })}
            className="flex items-center gap-1.5 text-xs rounded-control border border-border px-2.5 py-1.5 text-muted hover:text-text hover:border-accent"
          >
            <Download size={13} /> JSON report
          </a>
        </div>
      </header>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center rounded-control border border-border p-0.5 gap-0.5">
          {RANGE_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setRange(tab.value)}
              className={`px-2.5 py-1.5 text-xs rounded-[4px] transition-colors ${
                range === tab.value ? "bg-accent-soft text-accent font-medium" : "text-muted hover:text-text"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <select
          className="rounded-control border border-border bg-panel-alt px-2.5 py-1.5 text-xs"
          value={targetId ?? ""}
          onChange={(e) => setTargetId(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">All targets</option>
          {targets.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      {range === "custom" && (
        <div className="flex items-center gap-2">
          <input
            type="datetime-local"
            value={customStart}
            onChange={(e) => setCustomStart(e.target.value)}
            className="rounded-control border border-border bg-panel-alt px-2.5 py-1.5 text-xs"
          />
          <span className="text-muted text-xs">to</span>
          <input
            type="datetime-local"
            value={customEnd}
            onChange={(e) => setCustomEnd(e.target.value)}
            className="rounded-control border border-border bg-panel-alt px-2.5 py-1.5 text-xs"
          />
        </div>
      )}

      {statsLoading && !stats && <LoadingState />}
      {statsError && <ErrorState message={statsError} />}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <Stat label="Uptime" value={stats.uptime_pct !== null ? `${stats.uptime_pct.toFixed(2)}%` : "—"} />
          <Stat label="Avg latency" value={formatLatency(stats.avg_latency_ms)} />
          <Stat label="Min / Max" value={`${formatLatency(stats.min_latency_ms)} / ${formatLatency(stats.max_latency_ms)}`} />
          <Stat label="Median" value={formatLatency(stats.median_latency_ms)} />
          <Stat label="p95" value={formatLatency(stats.p95_latency_ms)} />
          <Stat label="Packet loss" value={formatPct(stats.packet_loss_pct)} />
          <Stat label="Avg jitter" value={formatLatency(stats.avg_jitter_ms)} />
          <Stat label="Outages" value={String(stats.outage_count)} />
          <Stat label="Longest outage" value={formatDuration(stats.longest_outage_seconds)} />
          <Stat label="Monitoring duration" value={formatDuration(stats.monitoring_duration_seconds)} />
          <Stat label="Samples" value={String(stats.sample_count)} />
        </div>
      )}

      <LatencyChart
        measurements={measurements ?? []}
        targets={chartTargets}
        rangeMinutes={chartMinutes}
        onRangeChange={setChartMinutes}
        rangeOptions={HISTORY_CHART_RANGES}
      />

      <div className="rounded-card border border-border bg-panel p-4">
        <h3 className="text-sm font-medium mb-3">Outage history</h3>
        <OutageList outages={outages ?? []} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-border bg-panel p-3">
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-mono font-tabular text-sm">{value}</p>
    </div>
  );
}

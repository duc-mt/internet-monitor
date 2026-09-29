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
    <div className="space-y-6">
      <header className="sticky top-0 z-10 -mx-6 lg:-mx-8 -mt-6 lg:-mt-8 mb-6 px-6 lg:px-8 py-4 backdrop-blur-md bg-white/80 dark:bg-slate-900/80 border-b border-border flex items-center justify-between flex-wrap gap-3 transition-all-fast">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-text">History</h1>
          <p className="text-xs text-muted font-medium mt-0.5">
            Latency, packet loss, jitter, and outage history · Lịch sử độ trễ, tỷ lệ mất gói và các đợt gián đoạn
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={api.exportMeasurementsCsvUrl({ target_id: targetId })}
            className="flex items-center gap-1.5 text-xs rounded-control border border-border bg-panel px-3 py-1.5 text-muted hover:text-text hover:border-accent shadow-sm transition-all-fast"
          >
            <Download size={13} /> CSV
          </a>
          <a
            href={api.exportReportJsonUrl({ range, target_id: targetId, ...(rangeParams ?? {}) })}
            className="flex items-center gap-1.5 text-xs rounded-control border border-border bg-panel px-3 py-1.5 text-muted hover:text-text hover:border-accent shadow-sm transition-all-fast"
          >
            <Download size={13} /> JSON report
          </a>
        </div>
      </header>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center rounded-control border border-border p-0.5 gap-0.5 bg-panel-alt">
          {RANGE_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setRange(tab.value)}
              className={`px-3 py-1.5 text-xs rounded-[4px] transition-all-fast font-medium ${
                range === tab.value ? "bg-accent-soft text-accent font-semibold shadow-sm" : "text-muted hover:text-text"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <select
          className="rounded-control border border-border bg-panel-alt px-3 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent transition-all-fast"
          value={targetId ?? ""}
          onChange={(e) => setTargetId(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">All targets (Tất cả mục tiêu)</option>
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
            className="rounded-control border border-border bg-panel-alt px-3 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <span className="text-muted text-xs font-medium">to (đến)</span>
          <input
            type="datetime-local"
            value={customEnd}
            onChange={(e) => setCustomEnd(e.target.value)}
            className="rounded-control border border-border bg-panel-alt px-3 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
      )}

      {statsLoading && !stats && <LoadingState />}
      {statsError && <ErrorState message={statsError} />}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
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

      <div className="rounded-card border border-border bg-panel p-5 shadow-sm transition-all-fast">
        <h3 className="text-sm font-semibold tracking-tight text-text mb-3">Outage history · Lịch sử gián đoạn kết nối</h3>
        <OutageList outages={outages ?? []} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-border bg-panel p-3.5 transition-all-fast hover:-translate-y-0.5 hover:shadow-md hover:border-slate-400 dark:hover:border-slate-700">
      <p className="text-[10px] uppercase tracking-widest font-semibold text-muted">{label}</p>
      <p className="mt-1 font-mono font-bold font-tabular text-sm text-text">{value}</p>
    </div>
  );
}

export type Protocol = "icmp" | "tcp";
export type Quality = "excellent" | "good" | "fair" | "poor" | "offline" | "unknown";
export type Stability = "excellent" | "good" | "fair" | "poor" | "unknown";
export type Theme = "light" | "dark" | "system";
export type RangeName = "1h" | "24h" | "7d" | "30d" | "custom";

export interface Target {
  id: number;
  name: string;
  host: string;
  protocol: Protocol;
  port: number | null;
  is_gateway: boolean;
  enabled: boolean;
  interval_seconds: number;
  created_at: string;
}

export type TargetInput = Omit<Target, "id" | "created_at">;

export interface Measurement {
  id: number;
  target_id: number;
  target_name?: string | null;
  timestamp: string;
  latency_ms: number | null;
  packet_loss: number;
  jitter_ms: number | null;
  success: boolean;
  error: string | null;
  network_name?: string | null;
  // Burst Probing summary (ms). null on checks recorded before the upgrade, or when every probe was lost.
  // Hourly rollup rows (error === "Downsampled") carry the hour's averages here.
  median_ms?: number | null;
  p25_ms?: number | null;
  p75_ms?: number | null;
  p95_ms?: number | null;
  min_ms?: number | null;
  max_ms?: number | null;
  iqr_ms?: number | null;
  jitter_rfc3550?: number | null;
  packet_count?: number | null;
}

export interface Outage {
  id: number;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  reason: string | null;
  affected_targets: string[];
  failed_checks: number;
  is_active: boolean;
}

export interface TargetStatus {
  target_id: number;
  name: string;
  host: string;
  reachable: boolean;
  latency_ms: number | null;
  packet_loss: number | null;
  last_checked: string | null;
  median_ms?: number | null;
  iqr_ms?: number | null;
  p95_ms?: number | null;
  jitter_rfc3550_ms?: number | null;
}

export interface StatusResponse {
  online: boolean;
  quality: Quality;
  latency_ms: number | null;
  packet_loss: number | null;
  jitter_ms: number | null;
  // Headline Burst Probing figures: mean over the non-gateway targets' latest bursts.
  median_ms?: number | null;
  iqr_ms?: number | null;
  p95_ms?: number | null;
  jitter_rfc3550_ms?: number | null;
  stability?: Stability;
  network_name?: string | null;
  monitoring_uptime_seconds: number;
  uptime_pct_24h: number | null;
  targets_reachable: number;
  targets_total: number;
  targets: TargetStatus[];
  active_outage: boolean;
  monitoring_running: boolean;
}

export interface StatisticsResponse {
  range_start: string;
  range_end: string;
  target_id: number | null;
  sample_count: number;
  avg_latency_ms: number | null;
  min_latency_ms: number | null;
  max_latency_ms: number | null;
  median_latency_ms: number | null;
  p95_latency_ms: number | null;
  packet_loss_pct: number | null;
  avg_jitter_ms: number | null;
  avg_iqr_ms?: number | null;
  uptime_pct: number | null;
  outage_count: number;
  longest_outage_seconds: number | null;
  monitoring_duration_seconds: number;
  downtime_seconds: number;
  effective_monitored_seconds: number;
}

export type HopScope = "private" | "cgnat" | "public" | "unknown";

export interface TracerouteHop {
  hop: number;
  address: string | null;
  rtts_ms: (number | null)[];
  avg_ms: number | null;
  loss_pct: number;
  scope: HopScope;
  extra_addresses: string[];
}

export interface TracerouteResult {
  target_id: number;
  target_name: string;
  host: string;
  hops: TracerouteHop[];
  raw: string;
  timed_out: boolean;
  elapsed_seconds: number;
}

export interface ClassificationThresholds {
  excellent_latency_ms: number;
  excellent_packet_loss_pct: number;
  good_latency_ms: number;
  good_packet_loss_pct: number;
  fair_latency_ms: number;
  fair_packet_loss_pct: number;
}

export interface StabilityThresholds {
  excellent_iqr_ms: number;
  good_iqr_ms: number;
  good_loss_pct: number;
  fair_iqr_ms: number;
  fair_loss_pct: number;
}

export interface NotificationPreferences {
  on_offline: boolean;
  on_online: boolean;
  on_latency_threshold: boolean;
  on_packet_loss_threshold: boolean;
  on_outage_duration: boolean;
  cooldown_seconds: number;
  webhook_url: string | null;
}

export interface AppSettings {
  ping_timeout_seconds: number;
  burst_packet_count: number;
  burst_interval_ms: number;
  default_target_interval_seconds: number;
  latency_warning_threshold_ms: number;
  packet_loss_warning_threshold_pct: number;
  outage_threshold_checks: number;
  outage_notify_min_duration_seconds: number;
  sla_target_pct: number;
  notifications: NotificationPreferences;
  classification: ClassificationThresholds;
  stability: StabilityThresholds;
  raw_retention_days: number;
  data_retention_days: number;
  start_on_boot: boolean;
  theme: Theme;
  language: string;
}

export interface SpeedtestResult {
  download_mbps: number;
  bytes_downloaded: number;
  elapsed_seconds: number;
  server: string;
}

export type AppSettingsUpdate = Partial<
  Omit<AppSettings, "notifications" | "classification" | "stability"> & {
    notifications: Partial<NotificationPreferences>;
    classification: Partial<ClassificationThresholds>;
    stability: Partial<StabilityThresholds>;
  }
>;

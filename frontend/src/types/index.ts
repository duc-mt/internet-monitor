export type Protocol = "icmp" | "tcp";
export type Quality = "excellent" | "good" | "fair" | "poor" | "offline" | "unknown";
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
}

export interface StatusResponse {
  online: boolean;
  quality: Quality;
  latency_ms: number | null;
  packet_loss: number | null;
  jitter_ms: number | null;
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
  uptime_pct: number | null;
  outage_count: number;
  longest_outage_seconds: number | null;
  monitoring_duration_seconds: number;
}

export interface ClassificationThresholds {
  excellent_latency_ms: number;
  excellent_packet_loss_pct: number;
  good_latency_ms: number;
  good_packet_loss_pct: number;
  fair_latency_ms: number;
  fair_packet_loss_pct: number;
}

export interface NotificationPreferences {
  on_offline: boolean;
  on_online: boolean;
  on_latency_threshold: boolean;
  on_packet_loss_threshold: boolean;
  on_outage_duration: boolean;
  cooldown_seconds: number;
}

export interface AppSettings {
  ping_timeout_seconds: number;
  pings_per_check: number;
  default_target_interval_seconds: number;
  latency_warning_threshold_ms: number;
  packet_loss_warning_threshold_pct: number;
  outage_threshold_checks: number;
  outage_notify_min_duration_seconds: number;
  notifications: NotificationPreferences;
  classification: ClassificationThresholds;
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
  Omit<AppSettings, "notifications" | "classification"> & {
    notifications: Partial<NotificationPreferences>;
    classification: Partial<ClassificationThresholds>;
  }
>;

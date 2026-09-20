import type {
  AppSettings,
  AppSettingsUpdate,
  Measurement,
  Outage,
  RangeName,
  SpeedtestResult,
  StatisticsResponse,
  StatusResponse,
  Target,
  TargetInput,
} from "../types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Could not reach the Internet Monitor backend. Is the service running?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  getStatus: () => request<StatusResponse>("/status"),

  listTargets: () => request<Target[]>("/targets"),
  createTarget: (data: TargetInput) =>
    request<Target>("/targets", { method: "POST", body: JSON.stringify(data) }),
  updateTarget: (id: number, data: Partial<TargetInput>) =>
    request<Target>(`/targets/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteTarget: (id: number) => request<void>(`/targets/${id}`, { method: "DELETE" }),

  listMeasurements: (params: { target_id?: number; start?: string; end?: string; limit?: number } = {}) =>
    request<Measurement[]>(`/measurements${toQuery(params)}`),

  getStatistics: (params: { range: RangeName; start?: string; end?: string; target_id?: number }) =>
    request<StatisticsResponse>(`/statistics${toQuery(params)}`),

  listOutages: (params: { start?: string; end?: string; limit?: number } = {}) =>
    request<Outage[]>(`/outages${toQuery(params)}`),

  getSettings: () => request<AppSettings>("/settings"),
  updateSettings: (patch: AppSettingsUpdate) =>
    request<AppSettings>("/settings", { method: "PUT", body: JSON.stringify(patch) }),

  // Manual only - never called on a timer anywhere in the app.
  runSpeedtest: () => request<SpeedtestResult>("/speedtest", { method: "POST" }),

  startMonitoring: () => request<{ running: boolean }>("/monitoring/start", { method: "POST" }),
  stopMonitoring: () => request<{ running: boolean }>("/monitoring/stop", { method: "POST" }),

  exportMeasurementsCsvUrl: (params: { target_id?: number; start?: string; end?: string } = {}) =>
    `${BASE}/export/measurements.csv${toQuery(params)}`,
  exportReportJsonUrl: (params: { range: RangeName; start?: string; end?: string; target_id?: number }) =>
    `${BASE}/export/report.json${toQuery(params)}`,
};

function toQuery(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (entries.length === 0) return "";
  const search = new URLSearchParams(entries.map(([k, v]) => [k, String(v)]));
  return `?${search.toString()}`;
}

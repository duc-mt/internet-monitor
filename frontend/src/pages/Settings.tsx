import { useEffect, useState } from "react";
import { useSettings } from "../hooks/useSettings";
import { useTheme } from "../hooks/useTheme";
import { LoadingState, ErrorState } from "../components/States";
import type { AppSettings, Theme } from "../types";

const inputClass =
  "w-full rounded-control border border-border bg-panel-alt px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent";
const labelClass = "block text-xs font-medium text-muted mb-1";

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-border bg-panel p-5 shadow-sm transition-all-fast">
      <h3 className="text-sm font-semibold tracking-tight text-text">{title}</h3>
      {description && <p className="text-xs text-muted font-medium mt-0.5 mb-3">{description}</p>}
      <div className={description ? "" : "mt-3"}>{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className={labelClass}>{label}</label>
      {children}
    </div>
  );
}

export function Settings() {
  const { settings, loading, error, updateSettings } = useSettings();
  const { setTheme } = useTheme();
  const [form, setForm] = useState<AppSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settings && !form) setForm(settings);
  }, [settings, form]);

  if (loading && !form) return <LoadingState />;
  if (error && !form) return <ErrorState message={error} />;
  if (!form) return null;

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await updateSettings(form);
      setTheme(form.theme as Theme);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      <header className="sticky top-0 z-10 -mx-6 lg:-mx-8 -mt-6 lg:-mt-8 mb-6 px-6 lg:px-8 py-4 backdrop-blur-md bg-white/80 dark:bg-slate-900/80 border-b border-border flex items-center justify-between transition-all-fast">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-text">Settings</h1>
          <p className="text-xs text-muted font-medium mt-0.5">
            Thresholds, notifications, and monitoring behavior · Ngưỡng cảnh báo, thông báo sự cố và cơ chế giám sát
          </p>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="rounded-control bg-gradient-to-br from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white text-sm font-medium px-4 py-2 shadow-sm hover:shadow-md transition-all-fast hover:-translate-y-0.5 disabled:opacity-50"
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save changes"}
        </button>
      </header>

      <Section title="Monitoring · Cơ chế giám sát" description="How often and how aggressively targets are checked · Tần suất và số gói tin ping khi kiểm tra mục tiêu.">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Ping timeout (Thời gian chờ - giây)">
            <input
              type="number" step="0.1" min={0.2} max={30} className={inputClass}
              value={form.ping_timeout_seconds}
              onChange={(e) => setForm({ ...form, ping_timeout_seconds: Number(e.target.value) })}
            />
          </Field>
          <Field label="Pings per check (Số gói ping mỗi lần)">
            <input
              type="number" min={1} max={10} className={inputClass}
              value={form.pings_per_check}
              onChange={(e) => setForm({ ...form, pings_per_check: Number(e.target.value) })}
            />
          </Field>
          <Field label="Default interval for new targets (Chu kỳ mặc định cho mục tiêu mới - giây)">
            <input
              type="number" min={1} max={3600} className={inputClass}
              value={form.default_target_interval_seconds}
              onChange={(e) => setForm({ ...form, default_target_interval_seconds: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Section>

      <Section title="Alert thresholds · Ngưỡng cảnh báo" description="When latency or packet loss should be treated as a problem · Ngưỡng kích hoạt cảnh báo khi mạng suy hao hoặc mất gói.">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Latency warning threshold (Ngưỡng cảnh báo độ trễ - ms)">
            <input
              type="number" min={0} className={inputClass}
              value={form.latency_warning_threshold_ms}
              onChange={(e) => setForm({ ...form, latency_warning_threshold_ms: Number(e.target.value) })}
            />
          </Field>
          <Field label="Packet loss warning threshold (Ngưỡng cảnh báo mất gói - %)">
            <input
              type="number" min={0} max={100} className={inputClass}
              value={form.packet_loss_warning_threshold_pct}
              onChange={(e) => setForm({ ...form, packet_loss_warning_threshold_pct: Number(e.target.value) })}
            />
          </Field>
          <Field label="Outage detection threshold (Số lần lỗi liên tiếp xác định sự cố)">
            <input
              type="number" min={1} max={60} className={inputClass}
              value={form.outage_threshold_checks}
              onChange={(e) => setForm({ ...form, outage_threshold_checks: Number(e.target.value) })}
            />
          </Field>
          <Field label="Notify if outage lasts longer than (Chỉ thông báo nếu sự cố kéo dài hơn - giây)">
            <input
              type="number" min={0} className={inputClass}
              value={form.outage_notify_min_duration_seconds}
              onChange={(e) => setForm({ ...form, outage_notify_min_duration_seconds: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Section>

      <Section title="Quality classification · Phân loại chất lượng mạng" description="Boundaries used for the Excellent / Good / Fair / Poor badge · Tiêu chuẩn đánh giá cấp độ kết nối.">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Excellent: latency below (Độ trễ dưới - ms)">
            <input type="number" className={inputClass} value={form.classification.excellent_latency_ms}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, excellent_latency_ms: Number(e.target.value) } })} />
          </Field>
          <Field label="Excellent: loss below (Mất gói dưới - %)">
            <input type="number" className={inputClass} value={form.classification.excellent_packet_loss_pct}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, excellent_packet_loss_pct: Number(e.target.value) } })} />
          </Field>
          <div />
          <Field label="Good: latency below (Độ trễ dưới - ms)">
            <input type="number" className={inputClass} value={form.classification.good_latency_ms}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, good_latency_ms: Number(e.target.value) } })} />
          </Field>
          <Field label="Good: loss below (Mất gói dưới - %)">
            <input type="number" className={inputClass} value={form.classification.good_packet_loss_pct}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, good_packet_loss_pct: Number(e.target.value) } })} />
          </Field>
          <div />
          <Field label="Fair: latency below (Độ trễ dưới - ms)">
            <input type="number" className={inputClass} value={form.classification.fair_latency_ms}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, fair_latency_ms: Number(e.target.value) } })} />
          </Field>
          <Field label="Fair: loss below (Mất gói dưới - %)">
            <input type="number" className={inputClass} value={form.classification.fair_packet_loss_pct}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, fair_packet_loss_pct: Number(e.target.value) } })} />
          </Field>
        </div>
      </Section>

      <Section title="Notifications · Thông báo Desktop" description="Desktop notifications via notify-send · Thông báo tức thời trên màn hình máy tính.">
        <div className="space-y-3">
          {(
            [
              ["on_offline", "Internet connection goes offline (Mất kết nối Internet hoàn toàn)"],
              ["on_online", "Internet connection comes back online (Kết nối Internet được khôi phục)"],
              ["on_latency_threshold", "Latency exceeds the warning threshold (Độ trễ vượt ngưỡng cảnh báo)"],
              ["on_packet_loss_threshold", "Packet loss exceeds the warning threshold (Mất gói vượt ngưỡng cảnh báo)"],
              ["on_outage_duration", "An outage lasts longer than the configured duration (Sự cố kéo dài vượt mức quy định)"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2.5 text-sm text-text cursor-pointer">
              <input
                type="checkbox"
                checked={form.notifications[key]}
                onChange={(e) => setForm({ ...form, notifications: { ...form.notifications, [key]: e.target.checked } })}
                className="rounded"
              />
              {label}
            </label>
          ))}
          <div className="pt-2 max-w-sm">
            <Field label="Cooldown between repeated alerts (Thời gian chờ giữa các lần nhắc lại - giây)">
              <input
                type="number" min={0} max={3600} className={inputClass}
                value={form.notifications.cooldown_seconds}
                onChange={(e) => setForm({ ...form, notifications: { ...form.notifications, cooldown_seconds: Number(e.target.value) } })}
              />
            </Field>
          </div>
        </div>
      </Section>

      <Section title="Data & appearance · Dữ liệu & Giao diện">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Data retention (Thời gian lưu trữ dữ liệu - ngày)">
            <input
              type="number" min={1} max={3650} className={inputClass}
              value={form.data_retention_days}
              onChange={(e) => setForm({ ...form, data_retention_days: Number(e.target.value) })}
            />
          </Field>
          <Field label="Theme (Giao diện hiển thị)">
            <select
              className={inputClass}
              value={form.theme}
              onChange={(e) => setForm({ ...form, theme: e.target.value as Theme })}
            >
              <option value="system">System (Theo hệ điều hành)</option>
              <option value="light">Light (Sáng)</option>
              <option value="dark">Dark (Tối)</option>
            </select>
          </Field>
          <Field label="Language (Ngôn ngữ)">
            <input
              className={inputClass}
              value={form.language}
              onChange={(e) => setForm({ ...form, language: e.target.value })}
            />
          </Field>
        </div>
        <label className="flex items-center gap-2.5 text-sm mt-3 text-text cursor-pointer">
          <input
            type="checkbox"
            checked={form.start_on_boot}
            onChange={(e) => setForm({ ...form, start_on_boot: e.target.checked })}
            className="rounded"
          />
          Start on boot (Tự khởi động cùng hệ điều hành)
        </label>
        <p className="text-xs text-muted mt-1.5">
          Tùy chọn ghi nhận cấu hình. Để bật/tắt dịch vụ systemd thực tế, chạy{" "}
          <code className="font-mono bg-panel-alt px-1.5 py-0.5 rounded border border-border">internet-monitor service enable-boot</code>{" "}
          (yêu cầu sudo) — trang dashboard luôn chạy với quyền người dùng thông thường.
        </p>
      </Section>
    </div>
  );
}

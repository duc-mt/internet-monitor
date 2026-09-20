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
    <div className="rounded-card border border-border bg-panel p-4">
      <h3 className="text-sm font-medium">{title}</h3>
      {description && <p className="text-xs text-muted mt-0.5 mb-3">{description}</p>}
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
    <div className="space-y-5 pb-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Settings</h1>
          <p className="text-sm text-muted mt-0.5">Thresholds, notifications, and monitoring behavior.</p>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="rounded-control bg-accent text-bg text-sm font-medium px-4 py-2 hover:opacity-90 disabled:opacity-50"
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save changes"}
        </button>
      </header>

      <Section title="Monitoring" description="How often and how aggressively targets are checked.">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Ping timeout (seconds)">
            <input
              type="number" step="0.1" min={0.2} max={30} className={inputClass}
              value={form.ping_timeout_seconds}
              onChange={(e) => setForm({ ...form, ping_timeout_seconds: Number(e.target.value) })}
            />
          </Field>
          <Field label="Pings per check (retries)">
            <input
              type="number" min={1} max={10} className={inputClass}
              value={form.pings_per_check}
              onChange={(e) => setForm({ ...form, pings_per_check: Number(e.target.value) })}
            />
          </Field>
          <Field label="Default interval for new targets (seconds)">
            <input
              type="number" min={1} max={3600} className={inputClass}
              value={form.default_target_interval_seconds}
              onChange={(e) => setForm({ ...form, default_target_interval_seconds: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Section>

      <Section title="Alert thresholds" description="When latency or packet loss should be treated as a problem.">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Latency warning threshold (ms)">
            <input
              type="number" min={0} className={inputClass}
              value={form.latency_warning_threshold_ms}
              onChange={(e) => setForm({ ...form, latency_warning_threshold_ms: Number(e.target.value) })}
            />
          </Field>
          <Field label="Packet loss warning threshold (%)">
            <input
              type="number" min={0} max={100} className={inputClass}
              value={form.packet_loss_warning_threshold_pct}
              onChange={(e) => setForm({ ...form, packet_loss_warning_threshold_pct: Number(e.target.value) })}
            />
          </Field>
          <Field label="Outage detection threshold (consecutive failed checks)">
            <input
              type="number" min={1} max={60} className={inputClass}
              value={form.outage_threshold_checks}
              onChange={(e) => setForm({ ...form, outage_threshold_checks: Number(e.target.value) })}
            />
          </Field>
          <Field label="Notify if outage lasts longer than (seconds)">
            <input
              type="number" min={0} className={inputClass}
              value={form.outage_notify_min_duration_seconds}
              onChange={(e) => setForm({ ...form, outage_notify_min_duration_seconds: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Section>

      <Section title="Quality classification" description="Boundaries used for the Excellent / Good / Fair / Poor badge.">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Excellent: latency below (ms)">
            <input type="number" className={inputClass} value={form.classification.excellent_latency_ms}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, excellent_latency_ms: Number(e.target.value) } })} />
          </Field>
          <Field label="Excellent: loss below (%)">
            <input type="number" className={inputClass} value={form.classification.excellent_packet_loss_pct}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, excellent_packet_loss_pct: Number(e.target.value) } })} />
          </Field>
          <div />
          <Field label="Good: latency below (ms)">
            <input type="number" className={inputClass} value={form.classification.good_latency_ms}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, good_latency_ms: Number(e.target.value) } })} />
          </Field>
          <Field label="Good: loss below (%)">
            <input type="number" className={inputClass} value={form.classification.good_packet_loss_pct}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, good_packet_loss_pct: Number(e.target.value) } })} />
          </Field>
          <div />
          <Field label="Fair: latency below (ms)">
            <input type="number" className={inputClass} value={form.classification.fair_latency_ms}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, fair_latency_ms: Number(e.target.value) } })} />
          </Field>
          <Field label="Fair: loss below (%)">
            <input type="number" className={inputClass} value={form.classification.fair_packet_loss_pct}
              onChange={(e) => setForm({ ...form, classification: { ...form.classification, fair_packet_loss_pct: Number(e.target.value) } })} />
          </Field>
        </div>
      </Section>

      <Section title="Notifications" description="Desktop notifications via notify-send.">
        <div className="space-y-2.5">
          {(
            [
              ["on_offline", "Internet connection goes offline"],
              ["on_online", "Internet connection comes back online"],
              ["on_latency_threshold", "Latency exceeds the warning threshold"],
              ["on_packet_loss_threshold", "Packet loss exceeds the warning threshold"],
              ["on_outage_duration", "An outage lasts longer than the configured duration"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                checked={form.notifications[key]}
                onChange={(e) => setForm({ ...form, notifications: { ...form.notifications, [key]: e.target.checked } })}
              />
              {label}
            </label>
          ))}
          <div className="pt-1 max-w-xs">
            <Field label="Cooldown between repeated alerts (seconds)">
              <input
                type="number" min={0} max={3600} className={inputClass}
                value={form.notifications.cooldown_seconds}
                onChange={(e) => setForm({ ...form, notifications: { ...form.notifications, cooldown_seconds: Number(e.target.value) } })}
              />
            </Field>
          </div>
        </div>
      </Section>

      <Section title="Data & appearance">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Data retention (days)">
            <input
              type="number" min={1} max={3650} className={inputClass}
              value={form.data_retention_days}
              onChange={(e) => setForm({ ...form, data_retention_days: Number(e.target.value) })}
            />
          </Field>
          <Field label="Theme">
            <select
              className={inputClass}
              value={form.theme}
              onChange={(e) => setForm({ ...form, theme: e.target.value as Theme })}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </Field>
          <Field label="Language">
            <input
              className={inputClass}
              value={form.language}
              onChange={(e) => setForm({ ...form, language: e.target.value })}
            />
          </Field>
        </div>
        <label className="flex items-center gap-2.5 text-sm mt-3">
          <input
            type="checkbox"
            checked={form.start_on_boot}
            onChange={(e) => setForm({ ...form, start_on_boot: e.target.checked })}
          />
          Start on boot
        </label>
        <p className="text-xs text-muted mt-1">
          This records your preference. To actually enable or disable the systemd service, run{" "}
          <code className="font-mono bg-panel-alt px-1 py-0.5 rounded">internet-monitor service enable-boot</code>{" "}
          (requires sudo) — the dashboard itself never gains root privileges.
        </p>
      </Section>
    </div>
  );
}

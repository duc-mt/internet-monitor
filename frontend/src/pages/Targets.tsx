import { useState } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { useTargets } from "../hooks/useTargets";
import { Modal } from "../components/Modal";
import { LoadingState, EmptyState } from "../components/States";
import { ApiError } from "../services/api";
import type { Target, TargetInput } from "../types";

const inputClass =
  "w-full rounded-control border border-border bg-panel-alt px-3 py-2 text-sm text-text placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent";
const labelClass = "block text-xs font-medium text-muted mb-1";

const DEFAULT_FORM: TargetInput = {
  name: "",
  host: "",
  protocol: "icmp",
  port: null,
  is_gateway: false,
  enabled: true,
  interval_seconds: 5,
};

export function Targets() {
  const { targets, loading, createTarget, updateTarget, deleteTarget } = useTargets();
  const [editing, setEditing] = useState<Target | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Target | null>(null);

  return (
    <div className="space-y-6">
      <header className="sticky top-0 z-10 -mx-6 lg:-mx-8 -mt-6 lg:-mt-8 mb-6 px-6 lg:px-8 py-4 backdrop-blur-md bg-white/80 dark:bg-slate-900/80 border-b border-border flex items-center justify-between transition-all-fast">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-text">Targets</h1>
          <p className="text-xs text-muted font-medium mt-0.5">
            Hosts monitored for latency, loss, and jitter · Danh sách máy chủ đích giám sát độ trễ và mất gói
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1.5 rounded-control bg-gradient-to-br from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white text-sm font-medium px-3.5 py-2 shadow-sm hover:shadow-md transition-all-fast hover:-translate-y-0.5"
        >
          <Plus size={15} /> Add target
        </button>
      </header>

      <div className="rounded-card border border-border bg-panel shadow-sm transition-all-fast">
        {loading ? (
          <LoadingState />
        ) : targets.length === 0 ? (
          <EmptyState
            title="No targets yet"
            description="Add a target to start monitoring · Thêm máy chủ đích để bắt đầu thu thập dữ liệu giám sát."
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted uppercase tracking-widest border-b border-border">
                <th className="py-2.5 px-4 font-semibold">Name</th>
                <th className="py-2.5 px-4 font-semibold">Host</th>
                <th className="py-2.5 px-4 font-semibold">Protocol</th>
                <th className="py-2.5 px-4 font-semibold">Interval</th>
                <th className="py-2.5 px-4 font-semibold">Enabled</th>
                <th className="py-2.5 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {targets.map((t) => (
                <tr key={t.id} className="border-b border-border last:border-0 hover:bg-panel-alt/50 transition-colors">
                  <td className="py-2.5 px-4">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-text">{t.name}</span>
                      {t.is_gateway && (
                        <span className="text-[10px] font-mono font-semibold uppercase tracking-widest text-accent bg-accent-soft border border-accent/20 rounded-full px-2 py-0.5">
                          gateway
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 px-4 font-mono text-xs text-muted">
                    {t.host}
                    {t.protocol === "tcp" && t.port ? `:${t.port}` : ""}
                  </td>
                  <td className="py-2.5 px-4 uppercase text-xs text-muted font-mono">{t.protocol}</td>
                  <td className="py-2.5 px-4 font-mono font-tabular">{t.interval_seconds}s</td>
                  <td className="py-2.5 px-4">
                    <button
                      onClick={() => updateTarget(t.id, { enabled: !t.enabled })}
                      className={`h-5 w-9 rounded-full transition-all-fast relative ${t.enabled ? "bg-accent" : "bg-border"}`}
                      aria-label={t.enabled ? "Disable target" : "Enable target"}
                    >
                      <span
                        className={`absolute top-0.5 h-4 w-4 rounded-full bg-panel transition-transform ${
                          t.enabled ? "translate-x-4" : "translate-x-0.5"
                        }`}
                      />
                    </button>
                  </td>
                  <td className="py-2.5 px-4">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => setEditing(t)}
                        className="p-1.5 rounded-control text-muted hover:text-text hover:bg-panel-alt transition-all-fast"
                        aria-label="Edit"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => setPendingDelete(t)}
                        className="p-1.5 rounded-control text-muted hover:text-offline hover:bg-panel-alt transition-all-fast"
                        aria-label="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {creating && (
        <TargetFormModal
          initial={DEFAULT_FORM}
          title="Add target"
          onClose={() => setCreating(false)}
          onSubmit={async (data) => {
            await createTarget(data);
            setCreating(false);
          }}
        />
      )}

      {editing && (
        <TargetFormModal
          initial={editing}
          title="Edit target"
          onClose={() => setEditing(null)}
          onSubmit={async (data) => {
            await updateTarget(editing.id, data);
            setEditing(null);
          }}
        />
      )}

      {pendingDelete && (
        <Modal title="Delete target · Xóa mục tiêu" onClose={() => setPendingDelete(null)}>
          <p className="text-sm text-text">
            Delete <span className="font-semibold text-text">{pendingDelete.name}</span>? Its measurement history will also be removed.
          </p>
          <p className="text-xs text-muted mt-1">
            Toàn bộ dữ liệu đo lường liên quan sẽ bị xóa vĩnh viễn khỏi cơ sở dữ liệu.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setPendingDelete(null)}
              className="px-3.5 py-1.5 text-sm rounded-control border border-border text-muted hover:text-text hover:bg-panel-alt transition-all-fast"
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                await deleteTarget(pendingDelete.id);
                setPendingDelete(null);
              }}
              className="px-3.5 py-1.5 text-sm rounded-control bg-offline text-white hover:opacity-90 font-medium transition-all-fast shadow-sm"
            >
              Delete
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function TargetFormModal({
  initial,
  title,
  onClose,
  onSubmit,
}: {
  initial: TargetInput;
  title: string;
  onClose: () => void;
  onSubmit: (data: TargetInput) => Promise<void>;
}) {
  const [form, setForm] = useState<TargetInput>(initial);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(form);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save target.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div>
          <label className={labelClass}>Name (Tên gợi nhớ)</label>
          <input
            className={inputClass}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Gateway, Cloudflare DNS"
            required
          />
        </div>
        <div>
          <label className={labelClass}>Hostname or IP (Tên miền hoặc Địa chỉ IP)</label>
          <input
            className={inputClass}
            value={form.host}
            onChange={(e) => setForm({ ...form, host: e.target.value })}
            placeholder="1.1.1.1 or example.com"
            required
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelClass}>Protocol (Giao thức)</label>
            <select
              className={inputClass}
              value={form.protocol}
              onChange={(e) => setForm({ ...form, protocol: e.target.value as "icmp" | "tcp" })}
            >
              <option value="icmp">ICMP (Ping)</option>
              <option value="tcp">TCP (Port Check)</option>
            </select>
          </div>
          {form.protocol === "tcp" && (
            <div>
              <label className={labelClass}>Port (Cổng kết nối)</label>
              <input
                type="number"
                min={1}
                max={65535}
                className={inputClass}
                value={form.port ?? 443}
                onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
              />
            </div>
          )}
        </div>
        <div>
          <label className={labelClass}>Interval (Chu kỳ kiểm tra - giây)</label>
          <input
            type="number"
            min={1}
            max={3600}
            className={inputClass}
            value={form.interval_seconds}
            onChange={(e) => setForm({ ...form, interval_seconds: Number(e.target.value) })}
          />
        </div>
        <div className="flex items-center gap-4 pt-1">
          <label className="flex items-center gap-2 text-sm text-text cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_gateway}
              onChange={(e) => setForm({ ...form, is_gateway: e.target.checked })}
              className="rounded"
            />
            Gateway target (Mục tiêu Gateway)
          </label>
          <label className="flex items-center gap-2 text-sm text-text cursor-pointer">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="rounded"
            />
            Enabled (Kích hoạt)
          </label>
        </div>

        {error && <p className="text-xs text-offline font-medium">{error}</p>}

        <div className="pt-3 flex justify-end gap-2 border-t border-border mt-4">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 text-sm rounded-control border border-border text-muted hover:text-text hover:bg-panel-alt transition-all-fast"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-1.5 text-sm rounded-control bg-gradient-to-br from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white font-medium shadow-sm hover:shadow-md transition-all-fast disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

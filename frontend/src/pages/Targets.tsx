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
    <div className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Targets</h1>
          <p className="text-sm text-muted mt-0.5">Hosts monitored for latency, loss, and jitter.</p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1.5 rounded-control bg-accent text-bg text-sm font-medium px-3 py-2 hover:opacity-90 transition-opacity"
        >
          <Plus size={15} /> Add target
        </button>
      </header>

      <div className="rounded-card border border-border bg-panel">
        {loading ? (
          <LoadingState />
        ) : targets.length === 0 ? (
          <EmptyState title="No targets yet" description="Add a target to start monitoring." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted uppercase tracking-wide border-b border-border">
                <th className="py-2.5 px-4 font-medium">Name</th>
                <th className="py-2.5 px-4 font-medium">Host</th>
                <th className="py-2.5 px-4 font-medium">Protocol</th>
                <th className="py-2.5 px-4 font-medium">Interval</th>
                <th className="py-2.5 px-4 font-medium">Enabled</th>
                <th className="py-2.5 px-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {targets.map((t) => (
                <tr key={t.id} className="border-b border-border last:border-0">
                  <td className="py-2.5 px-4">
                    <div className="flex items-center gap-2">
                      {t.name}
                      {t.is_gateway && (
                        <span className="text-[10px] uppercase tracking-wide text-accent bg-accent-soft rounded-full px-1.5 py-0.5">
                          gateway
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 px-4 font-mono text-xs text-muted">
                    {t.host}
                    {t.protocol === "tcp" && t.port ? `:${t.port}` : ""}
                  </td>
                  <td className="py-2.5 px-4 uppercase text-xs text-muted">{t.protocol}</td>
                  <td className="py-2.5 px-4 font-mono">{t.interval_seconds}s</td>
                  <td className="py-2.5 px-4">
                    <button
                      onClick={() => updateTarget(t.id, { enabled: !t.enabled })}
                      className={`h-5 w-9 rounded-full transition-colors relative ${t.enabled ? "bg-accent" : "bg-border"}`}
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
                        className="p-1.5 rounded-control text-muted hover:text-text hover:bg-panel-alt"
                        aria-label="Edit"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => setPendingDelete(t)}
                        className="p-1.5 rounded-control text-muted hover:text-offline hover:bg-panel-alt"
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
        <Modal title="Delete target" onClose={() => setPendingDelete(null)}>
          <p className="text-sm text-text">
            Delete <span className="font-medium">{pendingDelete.name}</span>? Its measurement history will also be removed.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={() => setPendingDelete(null)}
              className="px-3 py-1.5 text-sm rounded-control border border-border text-muted hover:text-text"
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                await deleteTarget(pendingDelete.id);
                setPendingDelete(null);
              }}
              className="px-3 py-1.5 text-sm rounded-control bg-offline text-white hover:opacity-90"
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
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className={labelClass}>Name</label>
          <input
            className={inputClass}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </div>
        <div>
          <label className={labelClass}>Hostname or IP</label>
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
            <label className={labelClass}>Protocol</label>
            <select
              className={inputClass}
              value={form.protocol}
              onChange={(e) => setForm({ ...form, protocol: e.target.value as "icmp" | "tcp" })}
            >
              <option value="icmp">ICMP</option>
              <option value="tcp">TCP</option>
            </select>
          </div>
          {form.protocol === "tcp" && (
            <div>
              <label className={labelClass}>Port</label>
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
          <label className={labelClass}>Interval (seconds)</label>
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
          <label className="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={form.is_gateway}
              onChange={(e) => setForm({ ...form, is_gateway: e.target.checked })}
            />
            Gateway target
          </label>
          <label className="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            Enabled
          </label>
        </div>

        {error && <p className="text-xs text-offline">{error}</p>}

        <div className="pt-2 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded-control border border-border text-muted hover:text-text">
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-3 py-1.5 text-sm rounded-control bg-accent text-bg font-medium hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

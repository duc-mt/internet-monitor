import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Modal } from "./Modal";
import { ApiError, api } from "../services/api";
import type { HopScope, TracerouteHop, TracerouteResult } from "../types";

interface TraceTarget {
  id: number;
  name: string;
  host: string;
}

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "done"; result: TracerouteResult };

const SCOPE_LABEL: Record<HopScope, { label: string; className: string }> = {
  private: { label: "LAN", className: "text-accent bg-accent-soft border-accent/20" },
  cgnat: { label: "ISP · CGNAT", className: "text-degraded bg-degraded/10 border-degraded/20" },
  public: { label: "Internet", className: "text-muted bg-panel-alt border-border" },
  unknown: { label: "—", className: "text-muted border-transparent" },
};

const PROBES = 3;

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    // The API wraps string details in JSON quotes; strip them for display.
    return err.message.replace(/^"|"$/g, "");
  }
  return "Traceroute failed · Không thể chạy traceroute.";
}

function formatRtt(value: number | null | undefined): string {
  if (value === null || value === undefined) return "*";
  return `${value < 10 ? value.toFixed(2) : value.toFixed(1)} ms`;
}

export function TracerouteModal({ target, onClose }: { target: TraceTarget; onClose: () => void }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<"table" | "raw">("table");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    api
      .runTraceroute(target.id)
      .then((result) => {
        if (!cancelled) setState({ status: "done", result });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ status: "error", message: errorMessage(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [target.id, attempt]);

  const copyRaw = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (e.g. non-secure context) - the raw view can still be selected by hand */
    }
  };

  return (
    <Modal title={`Traceroute · ${target.name}`} onClose={onClose} size="xl">
      <p className="text-xs text-muted font-medium">
        <span className="font-mono text-text">{target.host}</span> · Hop 1 thường là router nhà, các hop kế tiếp thuộc
        hạ tầng ISP và Internet.
      </p>

      {state.status === "loading" && (
        <div className="mt-6 mb-4 flex items-center gap-3 text-sm text-muted" role="status">
          <span className="h-4 w-4 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          Tracing route… this can take up to a minute · Đang dò đường đi, có thể mất tới một phút.
        </div>
      )}

      {state.status === "error" && (
        <div className="mt-4 rounded-control border border-offline/30 bg-offline/10 px-3 py-2.5 text-sm text-offline" role="alert">
          {state.message}
        </div>
      )}

      {state.status === "done" && (
        <>
          {state.result.timed_out && (
            <div className="mt-4 rounded-control border border-degraded/30 bg-degraded/10 px-3 py-2 text-xs text-degraded font-medium">
              Time budget exceeded, showing the hops resolved so far · Hết thời gian, chỉ hiển thị các hop đã dò được.
            </div>
          )}

          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="flex items-center rounded-control border border-border p-0.5 gap-0.5 bg-panel-alt">
              {(["table", "raw"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`px-2.5 py-1 text-xs rounded-[4px] font-mono transition-all-fast ${
                    view === v ? "bg-accent-soft text-accent font-semibold shadow-sm" : "text-muted hover:text-text"
                  }`}
                >
                  {v === "table" ? "Hops" : "Raw output"}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-muted">{state.result.elapsed_seconds.toFixed(1)} s</span>
              <button
                onClick={() => copyRaw(state.result.raw)}
                className="flex items-center gap-1.5 text-xs rounded-control border border-border bg-panel px-2.5 py-1 text-muted hover:text-text hover:border-accent transition-all-fast"
              >
                {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "Copied" : "Copy"}
              </button>
              <button
                onClick={() => setAttempt((n) => n + 1)}
                className="text-xs rounded-control border border-border bg-panel px-2.5 py-1 text-muted hover:text-text hover:border-accent transition-all-fast"
              >
                Run again
              </button>
            </div>
          </div>

          {view === "raw" ? (
            <pre className="mt-3 overflow-x-auto rounded-control border border-border bg-panel-alt p-3 font-mono text-xs leading-relaxed text-text whitespace-pre">
              {state.result.raw || "(no output)"}
            </pre>
          ) : (
            <HopTable hops={state.result.hops} />
          )}
        </>
      )}
    </Modal>
  );
}

function HopTable({ hops }: { hops: TracerouteHop[] }) {
  if (hops.length === 0) {
    return <p className="mt-4 text-sm text-muted">No hops were returned · Không có hop nào được trả về.</p>;
  }
  const hasSilentHop = hops.some((h) => h.address === null);

  return (
    <>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] font-semibold tracking-wider text-muted uppercase border-b border-border">
              <th className="py-2 pr-3">Hop</th>
              <th className="py-2 pr-3">Address</th>
              {Array.from({ length: PROBES }, (_, i) => (
                <th key={i} className="py-2 pr-3">
                  RTT {i + 1}
                </th>
              ))}
              <th className="py-2 pr-3">Avg</th>
              <th className="py-2 pr-3">Loss</th>
              <th className="py-2">Segment</th>
            </tr>
          </thead>
          <tbody>
            {hops.map((h) => {
              const silent = h.address === null;
              const scope = SCOPE_LABEL[h.scope];
              return (
                <tr key={h.hop} className="border-b border-border last:border-0">
                  <td className="py-2 pr-3 font-mono text-xs text-muted">{h.hop}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-text">
                    {silent ? <span className="text-muted">* * *</span> : h.address}
                    {h.extra_addresses.length > 0 && (
                      <span className="block text-[10px] text-muted">+ {h.extra_addresses.join(", ")}</span>
                    )}
                  </td>
                  {Array.from({ length: PROBES }, (_, i) => (
                    <td key={i} className="py-2 pr-3 font-mono font-tabular text-xs">
                      {formatRtt(h.rtts_ms[i])}
                    </td>
                  ))}
                  <td className="py-2 pr-3 font-mono font-tabular text-xs text-text">
                    {h.avg_ms === null ? "—" : formatRtt(h.avg_ms)}
                  </td>
                  <td
                    className={`py-2 pr-3 font-mono font-tabular text-xs ${
                      !silent && h.loss_pct > 0 ? "text-degraded font-semibold" : "text-muted"
                    }`}
                  >
                    {h.loss_pct}%
                  </td>
                  <td className="py-2">
                    <span className={`text-[10px] font-mono font-semibold uppercase tracking-widest rounded-full border px-2 py-0.5 ${scope.className}`}>
                      {scope.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {hasSilentHop && (
        <p className="mt-3 text-xs text-muted">
          A hop showing <span className="font-mono">* * *</span> is often a router that ignores ICMP, not a fault: it only matters if
          later hops are also lost · Hop hiển thị <span className="font-mono">* * *</span> thường là router không phản hồi ICMP, chỉ đáng lo
          khi các hop phía sau cũng mất gói.
        </p>
      )}
    </>
  );
}

import { useState } from "react";
import { Gauge, Loader2 } from "lucide-react";
import { api, ApiError } from "../services/api";
import type { SpeedtestResult } from "../types";

type State = "idle" | "running" | "done" | "error";

export function SpeedtestButton() {
  const [state, setState] = useState<State>("idle");
  const [result, setResult] = useState<SpeedtestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setState("running");
    setError(null);
    try {
      const r = await api.runSpeedtest();
      setResult(r);
      setState("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Speed test failed.");
      setState("error");
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={run}
        disabled={state === "running"}
        className="flex items-center gap-1.5 text-xs rounded-control border border-border px-2.5 py-1.5 text-muted hover:text-text hover:border-accent disabled:opacity-60"
      >
        {state === "running" ? <Loader2 size={13} className="animate-spin" /> : <Gauge size={13} />}
        {state === "running" ? "Testing…" : "Run speed test"}
      </button>
      {state === "done" && result && (
        <span className="text-xs font-mono font-tabular text-text">
          {result.download_mbps.toFixed(1)} Mbps down
          <span className="text-muted"> · {result.bytes_downloaded / 1_000_000}MB in {result.elapsed_seconds}s</span>
        </span>
      )}
      {state === "error" && <span className="text-xs text-offline">{error}</span>}
    </div>
  );
}

import { useCallback } from "react";
import { api } from "../services/api";
import { usePolling } from "../hooks/usePolling";
import { OutageList } from "../components/OutageList";
import { LoadingState, ErrorState } from "../components/States";

export function Outages() {
  const fetcher = useCallback(() => api.listOutages({ limit: 500 }), []);
  const { data: outages, error, loading, refetch } = usePolling(fetcher, 15000);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-lg font-semibold">Outages</h1>
        <p className="text-sm text-muted mt-0.5">
          Recorded whenever every monitored external target fails for a run of consecutive checks.
        </p>
      </header>

      <div className="rounded-card border border-border bg-panel p-4">
        {loading && !outages ? (
          <LoadingState />
        ) : error && !outages ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : (
          <OutageList outages={outages ?? []} />
        )}
      </div>
    </div>
  );
}

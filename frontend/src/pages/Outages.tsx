import { useCallback } from "react";
import { api } from "../services/api";
import { usePolling } from "../hooks/usePolling";
import { OutageList } from "../components/OutageList";
import { LoadingState, ErrorState } from "../components/States";

export function Outages() {
  const fetcher = useCallback(() => api.listOutages({ limit: 500 }), []);
  const { data: outages, error, loading, refetch } = usePolling(fetcher, 15000);

  return (
    <div className="space-y-6">
      <header className="sticky top-0 z-10 -mx-6 lg:-mx-8 -mt-6 lg:-mt-8 mb-6 px-6 lg:px-8 py-4 backdrop-blur-md bg-white/80 dark:bg-slate-900/80 border-b border-border transition-all-fast">
        <h1 className="text-xl font-extrabold tracking-tight text-text">Outages</h1>
        <p className="text-xs text-muted font-medium mt-0.5">
          Recorded whenever every monitored external target fails for a run of consecutive checks · Ghi nhận khi toàn bộ các mục tiêu bên ngoài mất kết nối liên tục
        </p>
      </header>

      <div className="rounded-card border border-border bg-panel p-5 shadow-sm transition-all-fast">
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

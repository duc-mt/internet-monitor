import { useCallback, useEffect, useRef, useState } from "react";

interface PollingState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Polls `fetcher` every `intervalMs`, chaining setTimeout calls (rather than
 * setInterval) so a slow request never causes overlapping in-flight calls.
 * Pass intervalMs=0 to fetch exactly once.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  deps: unknown[] = []
): PollingState<T> & { refetch: () => Promise<void> } {
  const [state, setState] = useState<PollingState<T>>({ data: null, error: null, loading: true });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(async () => {
    try {
      const data = await fetcherRef.current();
      setState({ data, error: null, loading: false });
    } catch (err) {
      setState((prev) => ({ data: prev.data, error: describeError(err), loading: false }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const data = await fetcherRef.current();
        if (!cancelled) setState({ data, error: null, loading: false });
      } catch (err) {
        if (!cancelled) setState((prev) => ({ data: prev.data, error: describeError(err), loading: false }));
      } finally {
        if (!cancelled && intervalMs > 0) {
          timer = window.setTimeout(tick, intervalMs);
        }
      }
    };

    setState((prev) => ({ data: prev.data, error: prev.error, loading: prev.data === null }));
    void tick();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);

  return { ...state, refetch };
}

function describeError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

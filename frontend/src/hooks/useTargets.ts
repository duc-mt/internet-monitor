import { useCallback } from "react";
import { api } from "../services/api";
import { usePolling } from "./usePolling";
import type { Target, TargetInput } from "../types";

// Targets change rarely; poll gently just to reflect edits made elsewhere
// (e.g. the CLI) without the user needing to refresh the page.
const TARGETS_POLL_MS = 15000;

export function useTargets() {
  const fetcher = useCallback(() => api.listTargets(), []);
  const { data, error, loading, refetch } = usePolling<Target[]>(fetcher, TARGETS_POLL_MS);

  const createTarget = useCallback(
    async (input: TargetInput) => {
      const created = await api.createTarget(input);
      await refetch();
      return created;
    },
    [refetch]
  );

  const updateTarget = useCallback(
    async (id: number, patch: Partial<TargetInput>) => {
      const updated = await api.updateTarget(id, patch);
      await refetch();
      return updated;
    },
    [refetch]
  );

  const deleteTarget = useCallback(
    async (id: number) => {
      await api.deleteTarget(id);
      await refetch();
    },
    [refetch]
  );

  return { targets: data ?? [], error, loading, refetch, createTarget, updateTarget, deleteTarget };
}

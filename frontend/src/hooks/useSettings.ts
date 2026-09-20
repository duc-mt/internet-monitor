import { useCallback } from "react";
import { api } from "../services/api";
import { usePolling } from "./usePolling";
import type { AppSettings, AppSettingsUpdate } from "../types";

export function useSettings() {
  const fetcher = useCallback(() => api.getSettings(), []);
  const { data, error, loading, refetch } = usePolling<AppSettings>(fetcher, 0);

  const updateSettings = useCallback(
    async (patch: AppSettingsUpdate) => {
      const updated = await api.updateSettings(patch);
      await refetch();
      return updated;
    },
    [refetch]
  );

  return { settings: data, error, loading, refetch, updateSettings };
}

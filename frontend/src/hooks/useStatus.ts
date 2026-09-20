import { useCallback } from "react";
import { api } from "../services/api";
import { usePolling } from "./usePolling";

const STATUS_POLL_MS = 4000;

export function useStatus() {
  const fetcher = useCallback(() => api.getStatus(), []);
  return usePolling(fetcher, STATUS_POLL_MS);
}

"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/** Load data from the API; `reload()` re-fetches. Errors are ApiError for the error states. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const value = await loadRef.current();
      setData(value);
      setError(undefined);
      return value;
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(-1, String(e)));
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Fetching from the API is syncing with an external system; the loading flag is part of it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload, setData };
}

/** Run an action (POST etc.) with busy and error state. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(undefined);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(-1, String(e)));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, run, setError };
}

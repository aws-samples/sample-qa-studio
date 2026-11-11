import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../utils/api';

export interface ApiList<T> {
  items: T[];
  loading: boolean;
  error: string | null;
  /** Re-fetch `path`; resolves once the list (or the error) is in state. */
  reload: () => Promise<void>;
}

/**
 * Load a JSON array from `GET path` and keep it in state.
 *
 * - `path === null` means "don't fetch yet" (e.g. the team id is not known):
 *   the list is empty and not loading.
 * - The list is fetched on mount and whenever `path` changes.
 * - Only the most recent request may write state, so a slow earlier response
 *   never overwrites a newer one (or anything after unmount).
 * - A non-array response is treated as an empty list; a failure clears the
 *   list and sets `error` to the error message, or `errorFallback`.
 */
export function useApiList<T>(path: string | null, errorFallback: string): ApiList<T> {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(path !== null);
  const [error, setError] = useState<string | null>(null);
  const latestRequest = useRef(0);

  const reload = useCallback(async () => {
    const request = ++latestRequest.current;
    const isLatest = () => request === latestRequest.current;

    if (path === null) {
      setItems([]);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await api.get(path);
      if (isLatest()) setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      if (isLatest()) {
        setError((err as { message?: string } | null)?.message || errorFallback);
        setItems([]);
      }
    } finally {
      if (isLatest()) setLoading(false);
    }
  }, [path, errorFallback]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Invalidate in-flight requests on unmount.
  useEffect(() => () => {
    latestRequest.current += 1;
  }, []);

  return { items, loading, error, reload };
}

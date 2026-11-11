import { useEffect, useState } from 'react';
import { ApiHttpError } from '../../../utils/api';

/** Statuses that hide the cost card instead of showing an error (no view permission / route not deployed). */
const HIDDEN_STATUSES: ReadonlySet<number> = new Set([403, 404]);

const GENERIC_ERROR_MESSAGE = 'Failed to load cost data';

export interface CostsState<T> {
  /** Response body; `null` while loading, hidden or failed. */
  data: T | null;
  loading: boolean;
  /** Message for the in-card Alert; `null` when the request succeeded or the card is hidden. */
  error: string | null;
  /** The API answered 403 or 404 → the caller renders nothing. */
  hidden: boolean;
}

function initialState<T>(): CostsState<T> {
  return { data: null, loading: true, error: null, hidden: false };
}

function errorMessage(err: unknown): string {
  return err instanceof Error && err.message ? err.message : GENERIC_ERROR_MESSAGE;
}

/**
 * Loads one dimension's cost through `loader(id)` exactly once per `id`.
 *
 * `loader` must be a module-level function (`costsApi.application`,
 * `costsApi.usecase`); it is deliberately not an effect dependency so a new
 * closure per render cannot start a refetch loop.
 */
export function useCosts<T>(loader: (id: string) => Promise<T>, id: string): CostsState<T> {
  const [state, setState] = useState<CostsState<T>>(initialState);

  useEffect(() => {
    let cancelled = false;
    setState(initialState());
    loader(id).then(
      (data) => {
        if (cancelled) return;
        setState({ data, loading: false, error: null, hidden: false });
      },
      (err: unknown) => {
        if (cancelled) return;
        const status = (err as Partial<ApiHttpError>).status;
        if (status !== undefined && HIDDEN_STATUSES.has(status)) {
          setState({ data: null, loading: false, error: null, hidden: true });
          return;
        }
        setState({ data: null, loading: false, error: errorMessage(err), hidden: false });
      },
    );
    return () => { cancelled = true; };
  }, [id]);

  return state;
}

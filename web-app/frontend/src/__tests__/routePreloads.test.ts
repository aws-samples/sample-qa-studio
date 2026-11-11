import { describe, it, expect, vi } from 'vitest';
import { ROUTE_PRELOADS, preloadRoutes } from '../routePreloads';

describe('route preloads', () => {
  it('every entry resolves to a module with a default component (catches path typos)', async () => {
    const modules = await Promise.all(ROUTE_PRELOADS.map((load) => load()));
    modules.forEach((m) => expect(typeof (m as { default: unknown }).default).toBe('function'));
  }, 60000);

  it('preloadRoutes fires every entry and swallows failures', async () => {
    const ok = vi.fn().mockResolvedValue({});
    const failing = vi.fn().mockRejectedValue(new Error('offline'));
    const list = ROUTE_PRELOADS as Array<() => Promise<unknown>>;
    const saved = list.splice(0, list.length, ok, failing);
    try {
      expect(() => preloadRoutes()).not.toThrow();
      await Promise.resolve();
      expect(ok).toHaveBeenCalledTimes(1);
      expect(failing).toHaveBeenCalledTimes(1);
    } finally {
      list.splice(0, list.length, ...saved);
    }
  });
});

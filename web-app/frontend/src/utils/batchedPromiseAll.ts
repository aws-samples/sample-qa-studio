export function getEffectiveBatchSize(batchSize: number): number {
  return batchSize > 0 ? batchSize : 5;
}

/**
 * Execute an array of async tasks in sequential batches.
 * Prevents overwhelming backends with limited concurrency (e.g. Lambda reserved concurrency).
 */
export async function batchedPromiseAll<T>(
  items: T[],
  task: (item: T) => Promise<unknown>,
  batchSize: number = __APP_CONFIG__.lambdaConcurrency,
): Promise<Awaited<ReturnType<typeof task>>[]> {
  const results: Awaited<ReturnType<typeof task>>[] = [];

  const effectiveBatchSize = getEffectiveBatchSize(batchSize);

  for (let i = 0; i < items.length; i += effectiveBatchSize) {
    const batch = items.slice(i, i + effectiveBatchSize);
    const batchResults = await Promise.all(batch.map(task));
    results.push(...batchResults);
  }

  return results;
}

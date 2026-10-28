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

  // Guard against a non-positive batch size (e.g. lambdaConcurrency=0 for
  // unreserved Lambda concurrency) which would cause an infinite loop.
  const effectiveBatchSize = batchSize > 0 ? batchSize : 5;

  for (let i = 0; i < items.length; i += effectiveBatchSize) {
    const batch = items.slice(i, i + effectiveBatchSize);
    const batchResults = await Promise.all(batch.map(task));
    results.push(...batchResults);
  }

  return results;
}

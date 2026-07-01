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

  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    const batchResults = await Promise.all(batch.map(task));
    results.push(...batchResults);
  }

  return results;
}

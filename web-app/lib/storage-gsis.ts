import { AttributeType, GlobalSecondaryIndexProps, ProjectionType } from 'aws-cdk-lib/aws-dynamodb';

/**
 * Global secondary indexes on the main table, in the order they were introduced.
 *
 * DynamoDB / CloudFormation allow only ONE GSI creation or deletion per table
 * update. Existing stacks therefore have to gain new indexes one deploy at a
 * time; `scripts/deploy-storage.ts` does that by passing the `storageGsis`
 * context (an allowlist of index names) to intermediate deploys.
 *
 * Append new indexes to the end of this list; never reorder or rename.
 */
export const TABLE_GSIS: GlobalSecondaryIndexProps[] = [
  {
    // Query use case executions by suite execution ID
    indexName: 'suite-execution-index',
    partitionKey: { name: 'suite_execution_id', type: AttributeType.STRING },
    sortKey: { name: 'sk', type: AttributeType.STRING },
    projectionType: ProjectionType.ALL,
  },
  {
    // User team memberships (permissions feature)
    indexName: 'user-teams-index',
    partitionKey: { name: 'gsi1pk', type: AttributeType.STRING },
    sortKey: { name: 'gsi1sk', type: AttributeType.STRING },
    projectionType: ProjectionType.ALL,
  },
  {
    // Team-owned apps and shared-with grants (permissions feature)
    indexName: 'team-apps-index',
    partitionKey: { name: 'gsi2pk', type: AttributeType.STRING },
    sortKey: { name: 'gsi2sk', type: AttributeType.STRING },
    projectionType: ProjectionType.ALL,
  },
];

export const STORAGE_GSIS_CONTEXT_KEY = 'storageGsis';

/**
 * Return the GSIs to synthesize. With no allowlist every index is included.
 * With an allowlist (comma-separated names) only those indexes are included,
 * in TABLE_GSIS order. Unknown names are rejected so a typo can't silently
 * drop an index.
 */
export function selectGsis(allowlist?: string): GlobalSecondaryIndexProps[] {
  if (allowlist === undefined || allowlist.trim() === '') {
    return TABLE_GSIS;
  }
  const wanted = new Set(allowlist.split(',').map(n => n.trim()).filter(Boolean));
  const known = new Set(TABLE_GSIS.map(g => g.indexName));
  const unknown = [...wanted].filter(n => !known.has(n));
  if (unknown.length > 0) {
    throw new Error(`${STORAGE_GSIS_CONTEXT_KEY} contains unknown index name(s): ${unknown.join(', ')}`);
  }
  return TABLE_GSIS.filter(g => wanted.has(g.indexName));
}

/**
 * Plan the intermediate allowlists needed to go from the deployed indexes to
 * all of TABLE_GSIS, adding one index per step. The final step (all indexes)
 * is not included: callers always finish with a normal full deploy.
 *
 * Indexes that exist in the deployed table but not in TABLE_GSIS are kept in
 * every intermediate step so nothing is deleted mid-sequence.
 */
export function planGsiSteps(deployed: string[]): string[][] {
  const deployedSet = new Set(deployed);
  const missing = TABLE_GSIS.map(g => g.indexName).filter(n => !deployedSet.has(n));
  const steps: string[][] = [];
  const current = [...deployed];
  for (const name of missing.slice(0, -1)) {
    current.push(name);
    steps.push([...current]);
  }
  return steps;
}

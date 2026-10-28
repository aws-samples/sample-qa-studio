import { ITable } from 'aws-cdk-lib/aws-dynamodb';
import { PolicyStatement } from 'aws-cdk-lib/aws-iam';
import { Function } from 'aws-cdk-lib/aws-lambda';

/** Partition key of the OAuth client records (OAUTH_CLIENTS/{client_id}). */
export const OAUTH_CLIENTS_PK = 'OAUTH_CLIENTS';

/**
 * Let the API authorizer resolve an M2M client's team binding.
 *
 * - TABLE_NAME: table holding OAUTH_CLIENTS/{client_id} (team_id, team_role).
 * - WORKER_CLIENT_ID: the shared worker client, emitted as identityType 'worker'.
 * - dynamodb:GetItem only, restricted to the OAUTH_CLIENTS partition.
 */
export function configureAuthorizerClientBinding(
  authorizerLambda: Function,
  table: ITable,
  workerClientId: string,
): void {
  authorizerLambda.addEnvironment('TABLE_NAME', table.tableName);
  authorizerLambda.addEnvironment('WORKER_CLIENT_ID', workerClientId);
  authorizerLambda.addToRolePolicy(new PolicyStatement({
    actions: ['dynamodb:GetItem'],
    resources: [table.tableArn],
    conditions: {
      'ForAllValues:StringEquals': { 'dynamodb:LeadingKeys': [OAUTH_CLIENTS_PK] },
    },
  }));
}

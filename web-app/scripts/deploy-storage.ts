#!/usr/bin/env ts-node
/**
 * Deploy the storage stack, adding missing DynamoDB GSIs one per deploy.
 *
 * DynamoDB / CloudFormation reject a table update that creates more than one
 * GSI ("Cannot perform more than one GSI creation or deletion in a single
 * update"). Fresh stacks are fine (all GSIs may be declared at table
 * creation), but an existing stack that is behind by two or more indexes
 * needs intermediate deploys.
 *
 * This script reads the table's GSIs from the currently deployed template,
 * runs one `cdk deploy storage -c storageGsis=<allowlist>` per missing index
 * (except the last), then a normal full `cdk deploy storage`.
 */
import { CloudFormationClient, GetTemplateCommand } from '@aws-sdk/client-cloudformation';
import { execFileSync } from 'child_process';
import { loadConfig } from '../lib/config';
import { STORAGE_GSIS_CONTEXT_KEY, planGsiSteps } from '../lib/storage-gsis';

const config = loadConfig();
const region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || config.defaultRegion;
const stackName = `${config.baseName}-storage`;

async function getDeployedGsis(): Promise<string[] | null> {
  const client = new CloudFormationClient({ region });
  let body: string | undefined;
  try {
    const res = await client.send(new GetTemplateCommand({ StackName: stackName, TemplateStage: 'Original' }));
    body = res.TemplateBody;
  } catch (error: any) {
    if (error?.name === 'ValidationError' && /does not exist/.test(String(error?.message))) {
      return null; // first deploy: all GSIs can be created with the table
    }
    throw error;
  }
  const template = JSON.parse(body ?? '{}');
  const tables = Object.values<any>(template.Resources ?? {}).filter(r => r.Type === 'AWS::DynamoDB::Table');
  if (tables.length !== 1) {
    throw new Error(`Expected exactly one DynamoDB table in ${stackName}, found ${tables.length}`);
  }
  return (tables[0].Properties?.GlobalSecondaryIndexes ?? []).map((g: any) => g.IndexName);
}

function cdkDeployStorage(extraArgs: string[]): void {
  const args = ['cdk', 'deploy', 'storage', '--require-approval', 'never', '--exclusively', ...extraArgs];
  console.log(`▶ npx ${args.join(' ')}`);
  execFileSync('npx', args, { stdio: 'inherit' });
}

async function main(): Promise<void> {
  const deployed = await getDeployedGsis();
  if (deployed === null) {
    console.log(`${stackName} does not exist yet; deploying with all GSIs.`);
  } else {
    const steps = planGsiSteps(deployed);
    console.log(`${stackName} deployed GSIs: ${deployed.join(', ') || '(none)'}`);
    for (const allowlist of steps) {
      console.log(`Adding GSI step: ${allowlist[allowlist.length - 1]}`);
      cdkDeployStorage(['-c', `${STORAGE_GSIS_CONTEXT_KEY}=${allowlist.join(',')}`]);
    }
  }
  cdkDeployStorage([]);
}

main().catch(error => {
  console.error('❌ Storage deploy failed:', error);
  process.exit(1);
});

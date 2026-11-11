#!/usr/bin/env ts-node
/**
 * Deploy the api stack, first removing older explicit variable children
 * (e.g. `/applications/{id}`) that conflict with new `{proxy+}` resources.
 *
 * API Gateway allows one variable path part per parent, and CloudFormation
 * creates new resources before deleting old ones. If the deployed template
 * still has a conflicting child, this script runs one
 * `cdk deploy api -c apiDeferredProxies=<names>` (omits those proxies, so the
 * old children are deleted) and then a normal `cdk deploy api`.
 *
 * Note: the affected nested routes return 403/404 between the two deploys.
 */
import { CloudFormationClient, GetTemplateCommand } from '@aws-sdk/client-cloudformation';
import { execFileSync } from 'child_process';
import * as path from 'path';
import { loadConfig } from '../lib/config';
import { API_DEFERRED_PROXIES_CONTEXT_KEY, findConflictingProxies } from '../lib/api-proxies';

// Call the aws-cdk CLI by path. `npx cdk` must NOT be used from this package:
// if package.json ever declares a `bin` named "cdk" again, npm resolves
// `npx cdk` to the project's own bin — the result was a silent synth instead
// of a deploy.
const CDK_BIN = path.join(__dirname, '..', 'node_modules', '.bin', 'cdk');

const config = loadConfig();
const region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || config.defaultRegion;
const stackName = `${config.baseName}-api`;

async function getDeployedResources(): Promise<Record<string, any> | null> {
  const client = new CloudFormationClient({ region });
  try {
    const res = await client.send(new GetTemplateCommand({ StackName: stackName, TemplateStage: 'Original' }));
    return JSON.parse(res.TemplateBody ?? '{}').Resources ?? {};
  } catch (error: any) {
    if (error?.name === 'ValidationError' && /does not exist/.test(String(error?.message))) {
      return null;
    }
    throw error;
  }
}

function cdkDeployApi(extraArgs: string[]): void {
  const args = ['deploy', 'api', '--require-approval', 'never', '--exclusively', ...extraArgs];
  console.log(`▶ cdk ${args.join(' ')}`);
  execFileSync(CDK_BIN, args, { stdio: 'inherit' });
}

async function main(): Promise<void> {
  const resources = await getDeployedResources();
  const conflicts = resources === null ? [] : findConflictingProxies(resources);
  if (conflicts.length > 0) {
    console.log(`${stackName}: removing old variable children under ${conflicts.join(', ')} before adding {proxy+}`);
    cdkDeployApi(['-c', `${API_DEFERRED_PROXIES_CONTEXT_KEY}=${conflicts.join(',')}`]);
  }
  cdkDeployApi([]);
}

main().catch(error => {
  console.error('❌ API deploy failed:', error);
  process.exit(1);
});

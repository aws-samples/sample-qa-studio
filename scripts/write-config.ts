#!/usr/bin/env ts-node
import { CloudFormationClient, DescribeStacksCommand } from '@aws-sdk/client-cloudformation';
import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';

const baseName = process.argv[2];
const region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || 'us-east-1';

if (!baseName) {
  console.error('Usage: ts-node scripts/write-config.ts <baseName>');
  process.exit(1);
}

async function getStackOutputs(stackName: string) {
  const client = new CloudFormationClient({ region });
  try {
    const command = new DescribeStacksCommand({ StackName: stackName });
    const response = await client.send(command);

    const outputs: Record<string, string> = {};
    response.Stacks?.[0]?.Outputs?.forEach(output => {
      if (output.OutputKey && output.OutputValue) {
        outputs[output.OutputKey] = output.OutputValue;
      }
    });

    return outputs;
  } catch (error) {
    console.error(`Failed to get outputs for stack ${stackName}:`, error);
    return {};
  }
}

function writeConfig(path: string, content: any) {
  const dir = dirname(path);
  mkdirSync(dir, { recursive: true });
  writeFileSync(path, JSON.stringify(content, null, 2), 'utf-8');
  console.log(`✅ Written: ${path}`);
}

async function main() {
  console.log(`📝 Fetching stack outputs for base name: ${baseName}`);
  console.log(`🌍 Region: ${region}\n`);

  const authOutputs = await getStackOutputs(`${baseName}-auth`);
  const apiOutputs = await getStackOutputs(`${baseName}-api`);

  if (!authOutputs.UserPoolIdOutput || !authOutputs.UserPoolClientIdOutput) {
    console.error('❌ Missing auth stack outputs. Make sure auth stack is deployed.');
    process.exit(1);
  }

  // Write amplify configuration
  const amplifyConfig = {
    Auth: {
      Cognito: {
        userPoolId: authOutputs.UserPoolIdOutput,
        userPoolClientId: authOutputs.UserPoolClientIdOutput,
        region: region
      }
    }
  };

  writeConfig(
    join(__dirname, '..', 'frontend', 'src', 'amplifyconfiguration.json'),
    amplifyConfig
  );

  // Optionally write API config
  if (apiOutputs.ApiUrlOutput) {
    const apiConfig = {
      apiUrl: apiOutputs.ApiUrlOutput,
      region: region
    };

    writeConfig(
      join(__dirname, '..', 'frontend', 'src', 'api-config.json'),
      apiConfig
    );
  }

  console.log('\n✅ All configuration files written successfully');
}

main().catch((error) => {
  console.error('❌ Error:', error);
  process.exit(1);
});

#!/usr/bin/env ts-node
/**
 * Build the NovaActRecorder Chrome extension zip and upload it to S3.
 *
 * Buckets: ${account}-${baseName}-artefacts-${region} for the default region and
 *          every enabled region (one artefact bucket per region, see worker-stack)
 * Key:     extensions/nova-act-recorder.zip
 *
 * The wizard worker loads the extension from the artefact bucket of the
 * browser's region (AgentCore only reads a same-region bucket; see
 * EXTENSION_S3_PREFIX in wizard_worker.py), so every regional bucket needs it.
 */
import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import { join } from 'path';
import { loadConfig } from '../lib/config';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { STSClient, GetCallerIdentityCommand } from '@aws-sdk/client-sts';

const S3_KEY = 'extensions/nova-act-recorder.zip';

export interface ExtensionTarget { region: string; bucket: string }

/** One upload per artefact bucket: the default region plus every enabled region. */
export function extensionTargets(
  account: string,
  config: { baseName: string; defaultRegion: string; enabledRegions: string[] },
): ExtensionTarget[] {
  const regions = [...new Set([config.defaultRegion, ...config.enabledRegions])];
  return regions.map(region => ({ region, bucket: `${account}-${config.baseName}-artefacts-${region}` }));
}

async function main() {
  const config = loadConfig();
  const region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || config.defaultRegion;

  // Resolve AWS account ID
  const sts = new STSClient({ region });
  const { Account: account } = await sts.send(new GetCallerIdentityCommand({}));
  if (!account) {
    console.error('❌ Could not resolve AWS account ID');
    process.exit(1);
  }

  // 1. Build the extension zip
  const buildScript = join(__dirname, '..', '..', 'chrome-extension', 'build-extension.sh');
  const zipPath = join(__dirname, '..', '..', 'nova-act-recorder.zip');

  console.log('📦 Building extension zip…');
  execSync(`bash "${buildScript}" "${zipPath}"`, { stdio: 'inherit' });

  // 2. Upload to every regional artefact bucket
  const body = readFileSync(zipPath);
  for (const target of extensionTargets(account, config)) {
    console.log(`⬆  Uploading to s3://${target.bucket}/${S3_KEY}…`);
    await new S3Client({ region: target.region }).send(new PutObjectCommand({
      Bucket: target.bucket,
      Key: S3_KEY,
      Body: body,
      ContentType: 'application/zip',
    }));
    console.log(`✅ Extension uploaded to s3://${target.bucket}/${S3_KEY}`);
  }
}

if (require.main === module) {
  main().catch((err) => {
    console.error('❌ Extension upload failed:', err);
    process.exit(1);
  });
}

#!/usr/bin/env ts-node
/**
 * Build the NovaActRecorder Chrome extension zip and upload it to S3.
 *
 * Bucket:  ${account}-${baseName}-artefacts-${region}
 * Key:     extensions/nova-act-recorder.zip
 *
 * The worker already expects the extension at that location
 * (see EXTENSION_S3_PREFIX default in wizard_worker.py).
 */
import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import { join } from 'path';
import { loadConfig } from '../lib/config';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { STSClient, GetCallerIdentityCommand } from '@aws-sdk/client-sts';

const S3_KEY = 'extensions/nova-act-recorder.zip';

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

  const bucketName = `${account}-${config.baseName}-artefacts-${region}`;

  // 1. Build the extension zip
  const buildScript = join(__dirname, '..', '..', 'chrome-extension', 'build-extension.sh');
  const zipPath = join(__dirname, '..', '..', 'nova-act-recorder.zip');

  console.log('📦 Building extension zip…');
  execSync(`bash "${buildScript}" "${zipPath}"`, { stdio: 'inherit' });

  // 2. Upload to S3
  console.log(`⬆️  Uploading to s3://${bucketName}/${S3_KEY}…`);
  const s3 = new S3Client({ region });
  const body = readFileSync(zipPath);

  await s3.send(new PutObjectCommand({
    Bucket: bucketName,
    Key: S3_KEY,
    Body: body,
    ContentType: 'application/zip',
  }));

  console.log(`✅ Extension uploaded to s3://${bucketName}/${S3_KEY}`);
}

main().catch((err) => {
  console.error('❌ Extension upload failed:', err);
  process.exit(1);
});

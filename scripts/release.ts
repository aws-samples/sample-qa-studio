#!/usr/bin/env ts-node
import { execSync } from 'child_process';
import { readFileSync, writeFileSync, existsSync, mkdirSync, unlinkSync, statSync } from 'fs';
import { join } from 'path';

const RELEASE_DIR = join(__dirname, '..', 'release');

function exec(command: string, options: any = {}): void {
  console.log(`🔧 ${command}`);
  execSync(command, { stdio: 'inherit', ...options });
}

function execQuiet(command: string): string {
  return execSync(command, { encoding: 'utf-8' }).trim();
}

function checkGitStatus(): void {
  console.log('\n📋 Checking git status...');
  const status = execQuiet('git status --porcelain');

  if (status) {
    console.error('❌ Git working directory is not clean. Commit or stash changes first.');
    console.error(status);
    process.exit(1);
  }

  console.log('✅ Git working directory is clean');
}

function getCurrentVersion(): string {
  const packageJson = JSON.parse(readFileSync('package.json', 'utf-8'));
  return packageJson.version;
}

function bumpVersion(releaseType: string): string {
  console.log(`\n📦 Bumping version (${releaseType})...`);

  const currentVersion = getCurrentVersion();
  console.log(`   Current version: ${currentVersion}`);

  // Use npm version to bump
  execQuiet(`npm version ${releaseType} --no-git-tag-version`);

  const newVersion = getCurrentVersion();
  console.log(`   New version: ${newVersion}`);

  return newVersion;
}

function buildLambdas(): void {
  console.log('\n🔨 Building Lambda functions...');
  exec('npm run build:lambdas');
}

function createReleaseDir(): void {
  if (!existsSync(RELEASE_DIR)) {
    mkdirSync(RELEASE_DIR, { recursive: true });
  }
}

function createReleaseZip(version: string): string {
  console.log('\n📦 Creating release archive...');

  const zipName = `nova-act-qa-studio-v${version}.zip`;
  const zipPath = join(RELEASE_DIR, zipName);

  // Remove old zip if exists
  if (existsSync(zipPath)) {
    unlinkSync(zipPath);
  }

  // Create temp directory for release contents
  const tempDir = join(RELEASE_DIR, 'temp');
  if (existsSync(tempDir)) {
    exec(`rm -rf ${tempDir}`);
  }
  mkdirSync(tempDir, { recursive: true });

  console.log('   Copying files...');

  // Copy Lambda functions with proper structure (lambda/cmd/function_name/bootstrap)
  exec(`mkdir -p ${tempDir}/lambda/cmd`);
  const lambdaDirs = execQuiet('ls lambda/cmd').split('\n').filter(d => d.trim());
  lambdaDirs.forEach(dir => {
    const bootstrapPath = `lambda/cmd/${dir}/bootstrap`;
    if (existsSync(bootstrapPath)) {
      exec(`mkdir -p ${tempDir}/lambda/cmd/${dir}`);
      exec(`cp ${bootstrapPath} ${tempDir}/lambda/cmd/${dir}/`);
    }
  });

  // Copy frontend source (will be built during deployment)
  exec(`mkdir -p ${tempDir}/frontend`);
  exec(`cp -r frontend/src ${tempDir}/frontend/`);
  exec(`cp -r frontend/public ${tempDir}/frontend/`);
  exec(`cp frontend/package.json ${tempDir}/frontend/`);
  exec(`cp frontend/package-lock.json ${tempDir}/frontend/`);
  exec(`cp frontend/tsconfig.json ${tempDir}/frontend/`);
  exec(`cp frontend/vite.config.ts ${tempDir}/frontend/ 2>/dev/null || true`);
  exec(`cp frontend/.env-sample ${tempDir}/frontend/ 2>/dev/null || true`);

  // Copy worker source
  exec(`mkdir -p ${tempDir}/worker`);
  exec(`cp worker/*.py ${tempDir}/worker/`);
  exec(`cp worker/requirements.txt ${tempDir}/worker/`);
  exec(`cp worker/Dockerfile ${tempDir}/worker/`);

  // Copy CDK TypeScript source (not compiled)
  exec(`cp -r lib ${tempDir}/`);
  exec(`cp -r bin ${tempDir}/`);

  // Copy scripts
  exec(`mkdir -p ${tempDir}/scripts`);
  exec(`cp scripts/write-config.ts ${tempDir}/scripts/`);

  // Copy configuration files
  exec(`cp package.json ${tempDir}/`);
  exec(`cp package-lock.json ${tempDir}/`);
  exec(`cp tsconfig.json ${tempDir}/`);
  exec(`cp cdk.json ${tempDir}/`);
  exec(`cp configuration.json ${tempDir}/configuration.json.sample`);

  // Copy documentation
  exec(`cp README.md ${tempDir}/`);
  exec(`cp CHANGELOG.md ${tempDir}/`);
  exec(`cp LICENSE ${tempDir}/`);
  if (existsSync('CONTRIBUTING.md')) exec(`cp CONTRIBUTING.md ${tempDir}/`);
  if (existsSync('CODE_OF_CONDUCT.md')) exec(`cp CODE_OF_CONDUCT.md ${tempDir}/`);
  if (existsSync('SECURITY.md')) exec(`cp SECURITY.md ${tempDir}/`);

  // Create zip
  console.log('   Creating zip archive...');
  exec(`cd ${tempDir} && zip -r ../${zipName} . -q`);

  // Cleanup temp directory
  exec(`rm -rf ${tempDir}`);

  const stats = statSync(zipPath);
  const sizeMB = (stats.size / 1024 / 1024).toFixed(2);

  console.log(`✅ Release archive created: ${zipName} (${sizeMB} MB)`);

  return zipPath;
}

function cleanupBuildArtifacts(): void {
  console.log('\n🧹 Cleaning up build artifacts...');
  exec('npm run clean:lambdas');
  console.log('✅ Build artifacts cleaned');
}

function gitCommitAndTag(version: string): void {
  console.log('\n📝 Creating git commit and tag...');

  exec('git add package.json package-lock.json CHANGELOG.md');
  exec(`git commit -m "chore: release v${version}"`);
  exec(`git tag -a v${version} -m "Release v${version}"`);

  console.log(`✅ Created commit and tag v${version}`);
}

function pushToRemote(): void {
  console.log('\n🚀 Pushing to remote...');

  try {
    exec('git push');
    exec('git push --tags');
    console.log('✅ Pushed commits and tags to remote');
  } catch (error) {
    console.log('⚠️  Failed to push to remote. You may need to push manually:');
    console.log('   git push && git push --tags');
  }
}

function printSummary(version: string, zipPath: string): void {
  console.log('\n' + '='.repeat(60));
  console.log('🎉 Release Complete!');
  console.log('='.repeat(60));
  console.log(`\nVersion: v${version}`);
  console.log(`Release: ${zipPath}`);
  console.log(`\nNext steps:`);
  console.log(`1. Test the release archive`);
  console.log(`2. Upload to GitHub Releases (manual)`);
  console.log(`3. Update documentation if needed`);
  console.log('\n' + '='.repeat(60) + '\n');
}

function main(): void {
  const releaseType = process.argv[2];

  if (!['patch', 'minor', 'major', 'prerelease'].includes(releaseType)) {
    console.error('Usage: ts-node release.ts <patch|minor|major|prerelease>');
    process.exit(1);
  }

  console.log('🚀 Starting release process...\n');
  console.log(`Release type: ${releaseType}`);

  try {
    // Pre-flight checks
    checkGitStatus();

    // Bump version
    const newVersion = bumpVersion(releaseType);

    // Generate changelog
    console.log('\n📝 Generating changelog...');
    exec(`npx ts-node scripts/generate-changelog.ts ${newVersion}`);

    // Build Lambdas only (frontend will be built during deployment)
    buildLambdas();

    // Create release
    createReleaseDir();
    const zipPath = createReleaseZip(newVersion);

    // Cleanup
    cleanupBuildArtifacts();

    // Git operations
    gitCommitAndTag(newVersion);
    pushToRemote();

    // Summary
    printSummary(newVersion, zipPath);

  } catch (error) {
    console.error('\n❌ Release failed:', (error as Error).message);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

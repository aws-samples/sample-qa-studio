import * as fs from 'fs';
import * as path from 'path';
import { AssetHashType, DockerImage, DockerIgnoreStrategy, FileSystem, IgnoreMode } from 'aws-cdk-lib';
import { Asset } from 'aws-cdk-lib/aws-s3-assets';
import { Construct } from 'constructs';

/** Repo root: the Docker build context of web-app/worker/Dockerfile. */
export const REPO_ROOT = path.resolve(__dirname, '..', '..');
/** Dockerfile whose COPY paths are relative to REPO_ROOT. */
export const WORKER_DOCKERFILE = path.join(REPO_ROOT, 'web-app', 'worker', 'Dockerfile');
/** The one include/exclude rule set for the worker build context (the Dockerfile reads it too when built locally). */
export const WORKER_DOCKERIGNORE = path.join(REPO_ROOT, '.dockerignore');

/**
 * Patterns of the repo-root `.dockerignore`, comments and blank lines dropped.
 * Read at synth time so the ECS image build and the MicroVM code artifact
 * always share the same rules.
 */
export function readDockerignorePatterns(file: string = WORKER_DOCKERIGNORE): string[] {
  return fs
    .readFileSync(file, 'utf-8')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('#'));
}

/**
 * Performance-only companion to `readDockerignorePatterns`: the same rules
 * plus one explicit pattern per excluded directory (up to `depth` levels below
 * `root`) that CDK's walker would otherwise still descend into.
 *
 * CDK derives "may this directory be skipped entirely?" from the negations in
 * the rule set: `!web-app/worker/**` makes it treat every child of `web-app`
 * as potentially re-included, so `web-app/node_modules` and
 * `web-app/frontend/node_modules` (~70k entries, ~10 s) are walked just to be
 * dropped file by file. An explicit `web-app/node_modules` pattern prunes the
 * walk. Every added pattern is already ignored by the raw rules, so the set of
 * files that ends up in the artifact (and its hash) is unchanged.
 */
export function pruneExcludes(patterns: string[], root: string = REPO_ROOT, depth: number = 2): string[] {
  const strategy = new DockerIgnoreStrategy(root, patterns);
  const extra: string[] = [];
  const walk = (dir: string, level: number): void => {
    if (level > depth) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const absolute = path.join(dir, entry.name);
      const ignored = strategy.ignores(absolute);
      if (ignored && !strategy.completelyIgnores(absolute)) {
        extra.push(path.relative(root, absolute));
      } else if (!ignored) {
        walk(absolute, level + 1);
      }
    }
  };
  walk(root, 1);
  return [...patterns, ...extra];
}

/** `.dockerignore` rules of `repoRoot`, pruned for CDK's walker (see `pruneExcludes`). */
export function workerContextExcludes(repoRoot: string = REPO_ROOT): string[] {
  return pruneExcludes(readDockerignorePatterns(path.join(repoRoot, '.dockerignore')), repoRoot);
}

/**
 * Write the MicroVM code artifact tree into `outputDir`: the `.dockerignore`
 * filtered repo root (`web-app/worker/**` + `qa-studio-cli/**`) plus the
 * worker Dockerfile at the zip root, which is where the Lambda MicroVM image
 * build expects it. The Dockerfile's COPY paths stay valid because the rest
 * of the tree keeps its repo-root-relative layout.
 */
export function bundleWorkerImageContext(outputDir: string, repoRoot: string = REPO_ROOT): void {
  const exclude = workerContextExcludes(repoRoot);
  FileSystem.copyDirectory(repoRoot, outputDir, { exclude, ignoreMode: IgnoreMode.DOCKER });
  fs.copyFileSync(path.join(repoRoot, 'web-app', 'worker', 'Dockerfile'), path.join(outputDir, 'Dockerfile'));
}

/**
 * S3 asset holding the MicroVM image build context (see `bundleWorkerImageContext`).
 *
 * Bundling is always local (`tryBundle` returns true), so no container runtime
 * is involved; the `image` is a required placeholder that is never pulled.
 * The asset hash is the fingerprint of the filtered source tree, so the zip is
 * re-uploaded (and the image rebuilt) only when worker or CLI sources change.
 */
export class WorkerImageAsset extends Asset {
  constructor(scope: Construct, id: string) {
    super(scope, id, {
      path: REPO_ROOT,
      exclude: workerContextExcludes(),
      ignoreMode: IgnoreMode.DOCKER,
      assetHashType: AssetHashType.SOURCE,
      bundling: {
        image: DockerImage.fromRegistry('scratch'),
        local: {
          tryBundle(outputDir: string): boolean {
            bundleWorkerImageContext(outputDir);
            return true;
          },
        },
      },
    });
  }
}

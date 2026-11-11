import Badge from '@cloudscape-design/components/badge';

/**
 * Single source for everything the UI decides based on a usecase's
 * `test_platform` (snake_case, as the API returns it).
 *
 *  - `web`      — browser test; runs in the cloud worker, locally, or in CI.
 *  - `mobile`   — Device Farm; cloud execution, video from Device Farm.
 *  - `electron` — desktop app launched by the CI runner on a macOS host.
 *                 No cloud execution, no live view, no video.
 */
export type TestPlatform = 'web' | 'mobile' | 'electron';

export const TEST_PLATFORM_OPTIONS: ReadonlyArray<{ value: TestPlatform; label: string }> = [
  { value: 'web', label: 'Web' },
  { value: 'mobile', label: 'Mobile' },
  { value: 'electron', label: 'Electron' },
];

/** Mirrors `ELECTRON_CI_RUNNER_ONLY_ERROR` in the lambdas — same wording on purpose. */
export const ELECTRON_CI_RUNNER_ONLY_MESSAGE =
  'Electron usecases can only be executed by the CI runner (qa-studio run)';

/** Reverse-DNS identifier, e.g. com.example.app (Info.plist CFBundleIdentifier). */
export const BUNDLE_ID_PATTERN = /^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;

export const BUNDLE_ID_HELP =
  "Optional. The app's CFBundleIdentifier (e.g. com.example.desktop). The runner refuses to launch a packaged .app whose identifier differs.";

export function isValidBundleId(value: string): boolean {
  return BUNDLE_ID_PATTERN.test(value.trim());
}

export function normalizePlatform(value?: string | null): TestPlatform {
  return value === 'mobile' || value === 'electron' ? value : 'web';
}

export function isElectron(value?: string | null): boolean {
  return normalizePlatform(value) === 'electron';
}

/** Can "Trigger Execution" in the UI start this usecase in the cloud worker? */
export function supportsCloudExecution(value?: string | null): boolean {
  return !isElectron(value);
}

/** Only AgentCore (web) executions expose a live browser view. */
export function supportsLiveView(value?: string | null): boolean {
  return normalizePlatform(value) === 'web';
}

/** Only web and mobile usecases have a `starting_url` the runner navigates to. */
export function usesStartingUrl(value?: string | null): boolean {
  return !isElectron(value);
}

const BADGE: Record<TestPlatform, { label: string; color: 'grey' | 'blue' | 'green' }> = {
  web: { label: 'Web', color: 'grey' },
  mobile: { label: 'Mobile', color: 'blue' },
  electron: { label: 'Electron', color: 'green' },
};

export function PlatformBadge({ platform }: { platform?: string | null }) {
  const { label, color } = BADGE[normalizePlatform(platform)];
  return <Badge color={color}>{label}</Badge>;
}

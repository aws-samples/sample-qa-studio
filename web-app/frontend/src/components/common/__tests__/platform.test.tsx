import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import {
  ELECTRON_CI_RUNNER_ONLY_MESSAGE,
  PlatformBadge,
  TEST_PLATFORM_OPTIONS,
  isElectron,
  normalizePlatform,
  supportsCloudExecution,
  supportsLiveView,
  usesStartingUrl,
} from '../platform';

describe('platform helpers', () => {
  it('normalises unknown and missing values to web', () => {
    expect(normalizePlatform(undefined)).toBe('web');
    expect(normalizePlatform(null)).toBe('web');
    expect(normalizePlatform('')).toBe('web');
    expect(normalizePlatform('tauri')).toBe('web');
    expect(normalizePlatform('mobile')).toBe('mobile');
    expect(normalizePlatform('electron')).toBe('electron');
  });

  it('offers exactly the three platforms the API accepts', () => {
    expect(TEST_PLATFORM_OPTIONS.map((o) => o.value)).toEqual(['web', 'mobile', 'electron']);
  });

  it('electron is the only platform without cloud execution', () => {
    expect(supportsCloudExecution('web')).toBe(true);
    expect(supportsCloudExecution('mobile')).toBe(true);
    expect(supportsCloudExecution('electron')).toBe(false);
    expect(isElectron('electron')).toBe(true);
    expect(isElectron(undefined)).toBe(false);
  });

  it('only web has a live view', () => {
    expect(supportsLiveView(undefined)).toBe(true);
    expect(supportsLiveView('web')).toBe(true);
    expect(supportsLiveView('mobile')).toBe(false);
    expect(supportsLiveView('electron')).toBe(false);
  });

  it('electron has no starting url', () => {
    expect(usesStartingUrl('web')).toBe(true);
    expect(usesStartingUrl('mobile')).toBe(true);
    expect(usesStartingUrl('electron')).toBe(false);
  });

  it('keeps the CI-runner message identical to the API error string', () => {
    expect(ELECTRON_CI_RUNNER_ONLY_MESSAGE).toBe(
      'Electron usecases can only be executed by the CI runner (qa-studio run)',
    );
  });
});

describe('PlatformBadge', () => {
  it.each([
    ['web', 'Web'],
    ['mobile', 'Mobile'],
    ['electron', 'Electron'],
    [undefined, 'Web'],
  ])('renders %s as "%s"', (platform, label) => {
    render(<PlatformBadge platform={platform} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

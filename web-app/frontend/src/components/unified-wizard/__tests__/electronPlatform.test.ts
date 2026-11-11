import { describe, it, expect } from 'vitest';
import { getWizardSteps, getAvailableMethods } from '../getWizardSteps';
import { wizardReducer, initialWizardState } from '../wizardReducer';
import { validateBasicInfo, validatePlatformConfig } from '../validation';
import type { WizardState } from '../types';

function stateWith(partial: Partial<WizardState>): WizardState {
  return { ...initialWizardState, ...partial };
}

describe('unified wizard — electron platform', () => {
  it('offers only blank and user-journey creation methods', () => {
    expect(getAvailableMethods('electron')).toEqual(['blank', 'user-journey']);
    expect(getAvailableMethods('web')).toContain('interactive-wizard');
  });

  it('blank path gets an app configuration step, never browser or recording steps', () => {
    const titles = getWizardSteps('create-new', 'blank', 'electron').map((s) => s.title);
    expect(titles).toEqual([
      'How to start',
      'Platform selection',
      'Basic info',
      'Creation method',
      'App configuration',
      'Review & create',
    ]);
    expect(titles).not.toContain('Browser configuration');
    expect(titles).not.toContain('Setup & record');
  });

  it('user-journey path goes straight to describe & generate', () => {
    const titles = getWizardSteps('create-new', 'user-journey', 'electron').map((s) => s.title);
    expect(titles).toContain('Describe & generate');
    expect(titles).not.toContain('Setup & record');
  });

  it('switching to electron clears web and mobile fields and resets web-only methods', () => {
    const start = stateWith({
      testPlatform: 'web',
      creationMethod: 'interactive-wizard',
      mobilePlatform: 'IOS',
      blankConfig: {
        ...initialWizardState.blankConfig,
        startingUrl: 'https://x.test',
        browserPolicyFile: new File(['{}'], 'p.json'),
        appPackage: 'com.x',
        deviceArn: 'arn:x',
        bundleId: 'keep?',
      },
    });
    const next = wizardReducer(start, { type: 'SET_TEST_PLATFORM', payload: 'electron' });
    expect(next.testPlatform).toBe('electron');
    expect(next.creationMethod).toBeNull();
    expect(next.mobilePlatform).toBeNull();
    expect(next.blankConfig.startingUrl).toBe('');
    expect(next.blankConfig.browserPolicyFile).toBeNull();
    expect(next.blankConfig.appPackage).toBe('');
    expect(next.blankConfig.deviceArn).toBeNull();
    // bundleId is meaningful for electron too — a fresh platform starts blank.
    expect(next.blankConfig.bundleId).toBe('');
  });

  it('keeps a user-journey method when switching to electron', () => {
    const next = wizardReducer(
      stateWith({ testPlatform: 'web', creationMethod: 'user-journey' }),
      { type: 'SET_TEST_PLATFORM', payload: 'electron' },
    );
    expect(next.creationMethod).toBe('user-journey');
  });

  it('switching from electron back to web clears the bundle id', () => {
    const electron = stateWith({
      testPlatform: 'electron',
      blankConfig: { ...initialWizardState.blankConfig, bundleId: 'com.productharness.desktop' },
    });
    const next = wizardReducer(electron, { type: 'SET_TEST_PLATFORM', payload: 'web' });
    expect(next.blankConfig.bundleId).toBe('');
  });

  it('basic info does not require a starting URL for electron', () => {
    const errors = validateBasicInfo(stateWith({
      testPlatform: 'electron',
      basicInfo: { ...initialWizardState.basicInfo, applicationId: 'app-1', name: 'Harness', executionRegion: 'eu-central-1', modelId: 'nova-act-v1.0', startingUrl: '' },
    }));
    expect(errors).toEqual({});
  });

  it('app configuration is optional for electron (bundle id may be empty)', () => {
    expect(validatePlatformConfig(stateWith({ testPlatform: 'electron' }))).toEqual({});
  });

  it('rejects a malformed bundle id', () => {
    const errors = validatePlatformConfig(stateWith({
      testPlatform: 'electron',
      blankConfig: { ...initialWizardState.blankConfig, bundleId: 'not a bundle id' },
    }));
    expect(errors.bundleId).toMatch(/reverse-DNS/i);
  });
});

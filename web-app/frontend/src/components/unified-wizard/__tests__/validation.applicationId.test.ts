import { describe, it, expect } from 'vitest';
import { validateBasicInfo, validateUploadFile } from '../validation';
import { initialWizardState } from '../wizardReducer';
import type { WizardState } from '../types';

// Every use case belongs to an application; the API requires application_id
// (with edit access) on create, wizard start, template apply and import.

function withState(overrides: Partial<WizardState>): WizardState {
  return { ...initialWizardState, ...overrides };
}

const basicInfo = {
  ...initialWizardState.basicInfo,
  name: 'Login flow',
  startingUrl: 'https://example.test',
  executionRegion: 'us-east-1',
  modelId: 'nova-act-v1.0',
};

const file = new File(['{}'], 'export.json', { type: 'application/json' });

describe('unified wizard requires an application', () => {
  it('basic info without an application is invalid', () => {
    const errors = validateBasicInfo(withState({ testPlatform: 'web', basicInfo: { ...basicInfo, applicationId: '' } }));
    expect(errors.applicationId).toBe('Application is required');
  });

  it('basic info with an application has no application error', () => {
    const errors = validateBasicInfo(withState({ testPlatform: 'web', basicInfo: { ...basicInfo, applicationId: 'app-1' } }));
    expect(errors).toEqual({});
  });

  it('import without an application is invalid', () => {
    const errors = validateUploadFile(withState({
      basicInfo: { ...basicInfo, applicationId: '' },
      importConfig: { ...initialWizardState.importConfig, file },
    }));
    expect(errors.applicationId).toBe('Application is required');
  });

  it('import with an application and a file is valid', () => {
    const errors = validateUploadFile(withState({
      basicInfo: { ...basicInfo, applicationId: 'app-1' },
      importConfig: { ...initialWizardState.importConfig, file },
    }));
    expect(errors).toEqual({});
  });
});

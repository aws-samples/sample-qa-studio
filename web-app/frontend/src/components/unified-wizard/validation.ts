import type { WizardState } from './types';

// --- Parsed Import Data ---

export interface ParsedImportData {
  usecase: any;
  exportVersion: string;
  name: string;
  stepCount: number;
  variableCount: number;
  secretCount: number;
  exportDate?: string;
  region?: string;
}

// --- Parse Result ---

export type ParseImportResult =
  | { success: true; data: ParsedImportData }
  | { success: false; error: string };

// --- Per-Step Validation Functions ---

export function validateHowToStart(state: WizardState): Record<string, string> {
  if (!state.creationPath) {
    return { creationPath: 'Please select how you want to start' };
  }
  return {};
}

export function validateBasicInfo(state: WizardState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!state.basicInfo.name.trim()) {
    errors.name = 'Name is required';
  }
  if (state.testPlatform === 'web' && !state.basicInfo.startingUrl.trim()) {
    errors.startingUrl = 'Starting URL is required for web tests';
  }
  if (state.testPlatform === 'web' && state.basicInfo.startingUrl.trim()) {
    try {
      new URL(state.basicInfo.startingUrl.trim());
    } catch {
      errors.startingUrl = 'Please enter a valid URL (e.g. https://example.com)';
    }
  }
  if (!state.basicInfo.executionRegion) {
    errors.executionRegion = 'Execution region is required';
  }
  if (!state.basicInfo.modelId) {
    errors.modelId = 'Model is required';
  }
  return errors;
}

export function validatePlatformSelection(state: WizardState): Record<string, string> {
  return {};
}

export function validateCreationMethod(state: WizardState): Record<string, string> {
  if (!state.creationMethod) {
    return { creationMethod: 'Please select a creation method' };
  }
  return {};
}

export function validatePlatformConfig(state: WizardState): Record<string, string> {
  const errors: Record<string, string> = {};

  if (state.testPlatform === 'mobile' && !state.mobilePlatform) {
    errors.mobilePlatform = 'Please select a mobile platform';
  }

  if (state.testPlatform === 'mobile' && state.mobilePlatform === 'ANDROID') {
    if (!state.blankConfig.appPackage.trim()) {
      errors.appPackage = 'App Package is required';
    }
    if (!state.blankConfig.appActivity.trim()) {
      errors.appActivity = 'App Activity is required';
    }
  }

  if (state.testPlatform === 'mobile' && state.mobilePlatform === 'IOS') {
    if (!state.blankConfig.bundleId.trim()) {
      errors.bundleId = 'Bundle ID is required';
    }
  }

  if (state.testPlatform === 'mobile' && state.mobilePlatform && !state.blankConfig.deviceArn) {
    errors.deviceArn = 'Please select a device';
  }

  return errors;
}

export function validateSelectSource(state: WizardState): Record<string, string> {
  if (!state.cloneConfig.selectedUsecaseId) {
    return { selectedUsecaseId: 'Please select a source use case' };
  }
  return {};
}

export function validateUploadFile(state: WizardState): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!state.importConfig.file) {
    errors.file = 'Please upload a JSON file';
  }

  if (state.importConfig.parseError) {
    errors.parseError = state.importConfig.parseError;
  }

  return errors;
}

export function validateSelectTemplate(state: WizardState): Record<string, string> {
  if (!state.templateConfig.selectedTemplateId) {
    return { selectedTemplateId: 'Please select a template' };
  }
  return {};
}

export function validateDescribeAndGenerate(state: WizardState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!state.userJourneyConfig.userJourneyText.trim()) {
    errors.userJourneyText = 'User journey description is required';
  }
  if (!state.userJourneyConfig.generatedUsecase) {
    errors.generatedUsecase = 'Please generate a use case before proceeding';
  }
  return errors;
}

// --- Step Title → Validation Function Mapping ---

const stepValidationMap: Record<string, (state: WizardState) => Record<string, string>> = {
  'How to start': validateHowToStart,
  'Basic info': validateBasicInfo,
  'Platform selection': validatePlatformSelection,
  'Creation method': validateCreationMethod,
  'Browser configuration': validatePlatformConfig,
  'App configuration': validatePlatformConfig,
  'Select source': validateSelectSource,
  'Upload file': validateUploadFile,
  'Select template': validateSelectTemplate,
  'Describe & generate': validateDescribeAndGenerate,
};

/**
 * Returns the validation function for a given step title.
 * Returns a no-op validator (empty errors) for steps without validation
 * (e.g. "Review & create", "Setup & record", "Describe & generate").
 */
export function getStepValidation(
  stepTitle: string
): (state: WizardState) => Record<string, string> {
  return stepValidationMap[stepTitle] ?? (() => ({}));
}

// --- Import File Parsing ---

/**
 * Parses an import JSON string and validates required fields.
 *
 * - Validates JSON syntax
 * - Validates required `usecase` and `exportVersion` fields
 * - Extracts metadata: name, step count, variable count, secret count, export date, region
 */
export function parseImportFile(fileContent: string): ParseImportResult {
  let parsed: any;

  try {
    parsed = JSON.parse(fileContent);
  } catch {
    return { success: false, error: 'Invalid JSON format' };
  }

  if (!parsed.usecase) {
    return { success: false, error: 'Missing required field: usecase' };
  }

  if (!parsed.exportVersion) {
    return { success: false, error: 'Missing required field: exportVersion' };
  }

  const usecase = parsed.usecase;

  const data: ParsedImportData = {
    usecase,
    exportVersion: parsed.exportVersion,
    name: usecase.name ?? '',
    stepCount: Array.isArray(parsed.steps) ? parsed.steps.length : 0,
    variableCount: Array.isArray(parsed.variables) ? parsed.variables.length : 0,
    secretCount: Array.isArray(parsed.secrets) ? parsed.secrets.length : 0,
    exportDate: parsed.exportedAt ?? undefined,
    region: usecase.region ?? undefined,
  };

  return { success: true, data };
}

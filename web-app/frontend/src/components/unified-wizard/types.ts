import React from 'react';

// --- Union Types ---

export type CreationPath = 'create-new' | 'clone' | 'import' | null;

export type CreationMethod = 'blank' | 'interactive-wizard' | 'template' | 'user-journey' | null;

export type TestPlatform = 'web' | 'mobile';

// --- Nested Config Interfaces ---

export interface BasicInfo {
  name: string;
  description: string;
  tags: string;
  executionRegion: string;
  modelId: string | null;
  startingUrl: string;
  active: boolean;
}

export interface BlankConfig {
  startingUrl: string;
  active: boolean;
  enableCache: boolean;
  browserPolicyFile: File | null;
  appPackage: string;
  appActivity: string;
  bundleId: string;
  deviceArn: string | null;
  appBinaryFile: File | null;
}

export interface InteractiveConfig {
  startingUrl: string;
  browserRegion: string;
  sessionId: string | null;
  usecaseId: string | null;
  sessionStatus: 'idle' | 'starting' | 'active' | 'finished' | 'error';
  sessionError: string | null;
  steps: any[];
  isNavHidden: boolean;
}

export interface TemplateDetail {
  id: string;
  name: string;
  description: string;
  starting_url?: string;
  active?: boolean;
  tags?: string[];
  steps?: any[];
  variables?: any[];
}

export interface TemplateConfig {
  selectedTemplateId: string | null;
  templateDetail: TemplateDetail | null;
  startingUrl: string;
  description: string;
}

export interface UserJourneyConfig {
  startingUrl: string;
  userJourneyText: string;
  executionRegion: string;
  isGenerating: boolean;
  generatedUsecase: any | null;
  previewMode: boolean;
  appPackage: string;
  appActivity: string;
  bundleId: string;
}

export interface UsecaseDetail {
  id: string;
  name: string;
  description: string;
  starting_url?: string;
  active?: boolean;
  tags?: string[];
  steps?: any[];
  variables?: any[];
  headers?: Record<string, string>;
}

export interface CloneConfig {
  selectedUsecaseId: string | null;
  usecaseDetail: UsecaseDetail | null;
  newName: string;
}

export interface ImportConfig {
  file: File | null;
  parsedData: any | null;
  parseError: string | null;
  missingSecrets: string[];
  secretValues: Record<string, string>;
}

// --- Wizard State ---

export interface WizardState {
  activeStepIndex: number;
  creationPath: CreationPath;
  basicInfo: BasicInfo;
  testPlatform: TestPlatform;
  mobilePlatform: string | null;
  creationMethod: CreationMethod;
  blankConfig: BlankConfig;
  interactiveConfig: InteractiveConfig;
  templateConfig: TemplateConfig;
  userJourneyConfig: UserJourneyConfig;
  cloneConfig: CloneConfig;
  importConfig: ImportConfig;
  isSubmitting: boolean;
  submitError: string | null;
}

// --- Wizard Actions (Discriminated Union) ---

export type WizardAction =
  // Navigation
  | { type: 'SET_ACTIVE_STEP'; payload: number }
  | { type: 'NEXT_STEP' }
  | { type: 'PREVIOUS_STEP' }
  // Step 1: How to Start
  | { type: 'SET_CREATION_PATH'; payload: CreationPath }
  // Step 2: Basic Info
  | { type: 'UPDATE_BASIC_INFO'; payload: Partial<BasicInfo> }
  // Step 3: Platform Selection
  | { type: 'SET_TEST_PLATFORM'; payload: TestPlatform }
  | { type: 'SET_MOBILE_PLATFORM'; payload: string | null }
  // Step 4: Creation Method
  | { type: 'SET_CREATION_METHOD'; payload: CreationMethod }
  // Method-specific configs
  | { type: 'UPDATE_BLANK_CONFIG'; payload: Partial<BlankConfig> }
  | { type: 'UPDATE_INTERACTIVE_CONFIG'; payload: Partial<InteractiveConfig> }
  | { type: 'UPDATE_TEMPLATE_CONFIG'; payload: Partial<TemplateConfig> }
  | { type: 'UPDATE_USER_JOURNEY_CONFIG'; payload: Partial<UserJourneyConfig> }
  // Clone
  | { type: 'UPDATE_CLONE_CONFIG'; payload: Partial<CloneConfig> }
  // Import
  | { type: 'UPDATE_IMPORT_CONFIG'; payload: Partial<ImportConfig> }
  // Submission
  | { type: 'SUBMIT_START' }
  | { type: 'SUBMIT_SUCCESS' }
  | { type: 'SUBMIT_ERROR'; payload: string };

// --- Step Component Props ---

export interface StepProps {
  state: WizardState;
  dispatch: React.Dispatch<WizardAction>;
  validationErrors: Record<string, string>;
  onSubmit?: () => void;
  submitTrigger?: number;
}

// --- Wizard Step Configuration ---

export interface WizardStepConfig {
  title: string;
  description?: string;
  isOptional?: boolean;
  component: React.ComponentType<StepProps>;
}

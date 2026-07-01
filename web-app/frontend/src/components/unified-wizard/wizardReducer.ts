import type {
  WizardState,
  WizardAction,
  BlankConfig,
  InteractiveConfig,
  TemplateConfig,
  UserJourneyConfig,
  CloneConfig,
  ImportConfig,
  BasicInfo,
} from './types';

// --- Default Config Objects (exported for resets and testing) ---

export const defaultBasicInfo: BasicInfo = {
  name: '',
  description: '',
  tags: '',
  executionRegion: '',
  modelId: null,
  startingUrl: '',
  active: true,
  applicationId: '',
};

export const defaultBlankConfig: BlankConfig = {
  startingUrl: '',
  active: true,
  enableCache: false,
  browserPolicyFile: null,
  appPackage: '',
  appActivity: '',
  bundleId: '',
  deviceArn: null,
  appBinaryFile: null,
};

export const defaultInteractiveConfig: InteractiveConfig = {
  startingUrl: '',
  browserRegion: '',
  sessionId: null,
  usecaseId: null,
  sessionStatus: 'idle',
  sessionError: null,
  steps: [],
  isNavHidden: false,
};

export const defaultTemplateConfig: TemplateConfig = {
  selectedTemplateId: null,
  templateDetail: null,
  startingUrl: '',
  description: '',
};

export const defaultUserJourneyConfig: UserJourneyConfig = {
  startingUrl: '',
  userJourneyText: '',
  executionRegion: '',
  isGenerating: false,
  generatedUsecase: null,
  previewMode: false,
  appPackage: '',
  appActivity: '',
  bundleId: '',
};

export const defaultCloneConfig: CloneConfig = {
  selectedUsecaseId: null,
  usecaseDetail: null,
  newName: '',
};

export const defaultImportConfig: ImportConfig = {
  file: null,
  parsedData: null,
  parseError: null,
  missingSecrets: [],
  secretValues: {},
};

// --- Initial Wizard State ---

export const initialWizardState: WizardState = {
  activeStepIndex: 0,
  creationPath: null,
  basicInfo: { ...defaultBasicInfo },
  testPlatform: 'web',
  mobilePlatform: null,
  creationMethod: null,
  blankConfig: { ...defaultBlankConfig },
  interactiveConfig: { ...defaultInteractiveConfig },
  templateConfig: { ...defaultTemplateConfig },
  userJourneyConfig: { ...defaultUserJourneyConfig },
  cloneConfig: { ...defaultCloneConfig },
  importConfig: { ...defaultImportConfig },
  isSubmitting: false,
  submitError: null,
};

// --- Web-only creation methods ---

const WEB_ONLY_METHODS = new Set(['interactive-wizard', 'template']);

// --- Reducer ---

export function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    // --- Navigation ---

    case 'SET_ACTIVE_STEP':
      return { ...state, activeStepIndex: action.payload };

    case 'NEXT_STEP':
      return { ...state, activeStepIndex: state.activeStepIndex + 1 };

    case 'PREVIOUS_STEP':
      return { ...state, activeStepIndex: Math.max(0, state.activeStepIndex - 1) };

    // --- Step 1: How to Start ---

    case 'SET_CREATION_PATH':
      return {
        ...state,
        creationPath: action.payload,
        creationMethod: null,
        blankConfig: { ...defaultBlankConfig },
        interactiveConfig: { ...defaultInteractiveConfig },
        templateConfig: { ...defaultTemplateConfig },
        userJourneyConfig: { ...defaultUserJourneyConfig },
        cloneConfig: { ...defaultCloneConfig },
        importConfig: { ...defaultImportConfig },
        activeStepIndex: 0,
      };

    // --- Step 2: Basic Info ---

    case 'UPDATE_BASIC_INFO':
      return {
        ...state,
        basicInfo: { ...state.basicInfo, ...action.payload },
      };

    // --- Step 3: Platform Selection ---

    case 'SET_TEST_PLATFORM': {
      if (action.payload === state.testPlatform) {
        return state;
      }

      if (action.payload === 'mobile') {
        // Switching to mobile: clear web-specific fields, reset method if web-only
        const resetMethod = state.creationMethod !== null && WEB_ONLY_METHODS.has(state.creationMethod);
        return {
          ...state,
          testPlatform: 'mobile',
          creationMethod: resetMethod ? null : state.creationMethod,
          blankConfig: {
            ...state.blankConfig,
            startingUrl: '',
            browserPolicyFile: null,
          },
        };
      }

      // Switching to web: clear mobile-specific fields
      return {
        ...state,
        testPlatform: 'web',
        mobilePlatform: null,
        blankConfig: {
          ...state.blankConfig,
          appPackage: '',
          appActivity: '',
          bundleId: '',
          deviceArn: null,
          appBinaryFile: null,
        },
      };
    }

    case 'SET_MOBILE_PLATFORM':
      return {
        ...state,
        mobilePlatform: action.payload,
        blankConfig: {
          ...state.blankConfig,
          appPackage: '',
          appActivity: '',
          bundleId: '',
          deviceArn: null,
          appBinaryFile: null,
        },
      };

    // --- Step 4: Creation Method ---

    case 'SET_CREATION_METHOD': {
      const newState: WizardState = {
        ...state,
        creationMethod: action.payload,
      };

      // Reset all method-specific configs except the newly selected method
      if (action.payload !== 'blank') {
        newState.blankConfig = { ...defaultBlankConfig };
      }
      if (action.payload !== 'interactive-wizard') {
        newState.interactiveConfig = { ...defaultInteractiveConfig };
      }
      if (action.payload !== 'template') {
        newState.templateConfig = { ...defaultTemplateConfig };
      }
      if (action.payload !== 'user-journey') {
        newState.userJourneyConfig = { ...defaultUserJourneyConfig };
      }

      return newState;
    }

    // --- Method-specific updates ---

    case 'UPDATE_BLANK_CONFIG':
      return {
        ...state,
        blankConfig: { ...state.blankConfig, ...action.payload },
      };

    case 'UPDATE_INTERACTIVE_CONFIG':
      return {
        ...state,
        interactiveConfig: { ...state.interactiveConfig, ...action.payload },
      };

    case 'UPDATE_TEMPLATE_CONFIG':
      return {
        ...state,
        templateConfig: { ...state.templateConfig, ...action.payload },
      };

    case 'UPDATE_USER_JOURNEY_CONFIG':
      return {
        ...state,
        userJourneyConfig: { ...state.userJourneyConfig, ...action.payload },
      };

    // --- Clone ---

    case 'UPDATE_CLONE_CONFIG':
      return {
        ...state,
        cloneConfig: { ...state.cloneConfig, ...action.payload },
      };

    // --- Import ---

    case 'UPDATE_IMPORT_CONFIG':
      return {
        ...state,
        importConfig: { ...state.importConfig, ...action.payload },
      };

    // --- Submission ---

    case 'SUBMIT_START':
      return {
        ...state,
        isSubmitting: true,
        submitError: null,
      };

    case 'SUBMIT_SUCCESS':
      return {
        ...state,
        isSubmitting: false,
      };

    case 'SUBMIT_ERROR':
      return {
        ...state,
        isSubmitting: false,
        submitError: action.payload,
      };

    default:
      return state;
  }
}

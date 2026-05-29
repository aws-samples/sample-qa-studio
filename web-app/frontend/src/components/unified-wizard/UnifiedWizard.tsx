import { useReducer, useState, useMemo, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Wizard from "@cloudscape-design/components/wizard";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import SpaceBetween from "@cloudscape-design/components/space-between";
import { wizardReducer, initialWizardState } from './wizardReducer';
import { getWizardSteps } from './getWizardSteps';
import { getStepValidation } from './validation';

/**
 * UnifiedWizard — top-level page component at /create/new
 *
 * Renders a Cloudscape Wizard with dynamically computed steps based on
 * the user's selected creation path, creation method, and test platform.
 *
 * State is managed via useReducer (wizardReducer). Validation errors are
 * tracked in local state (UI-only concern, not part of the reducer).
 *
 * When the Interactive Wizard live session is active (isNavHidden), the
 * wizard chrome is hidden and the step content fills the page.
 */
export default function UnifiedWizard() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [state, dispatch] = useReducer(wizardReducer, initialWizardState);

  useEffect(() => {
    const appId = searchParams.get('applicationId');
    if (appId && !state.basicInfo.applicationId) {
      dispatch({ type: 'UPDATE_BASIC_INFO', payload: { applicationId: appId } });
    }
  }, [searchParams]);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [submitTrigger, setSubmitTrigger] = useState(0);

  // Compute the active wizard steps from current state
  const steps = useMemo(
    () => getWizardSteps(state.creationPath, state.creationMethod, state.testPlatform),
    [state.creationPath, state.creationMethod, state.testPlatform]
  );

  // Map WizardStepConfig[] to Cloudscape Wizard steps
  const wizardSteps = useMemo(
    () =>
      steps.map((config) => ({
        title: config.title,
        description: config.description,
        isOptional: config.isOptional,
        content: (
          <config.component
            state={state}
            dispatch={dispatch}
            validationErrors={validationErrors}
            submitTrigger={submitTrigger}
          />
        ),
      })),
    [steps, state, dispatch, validationErrors, submitTrigger]
  );

  const handleNavigate = (event: { detail: { requestedStepIndex: number; reason: string } }) => {
    const { requestedStepIndex, reason } = event.detail;

    if (reason === 'next') {
      // Validate current step before advancing
      const currentStepTitle = steps[state.activeStepIndex]?.title ?? '';
      const validate = getStepValidation(currentStepTitle);
      const errors = validate(state);

      if (Object.keys(errors).length > 0) {
        setValidationErrors(errors);
        return;
      }

      // Clear errors and advance
      setValidationErrors({});
      dispatch({ type: 'NEXT_STEP' });
    } else if (reason === 'previous') {
      // No validation needed when going back
      setValidationErrors({});
      dispatch({ type: 'PREVIOUS_STEP' });
    } else if (reason === 'step') {
      // Clicking a completed step in the nav panel
      setValidationErrors({});
      dispatch({ type: 'SET_ACTIVE_STEP', payload: requestedStepIndex });
    }
  };

  const handleCancel = () => {
    navigate('/');
  };

  // When the Interactive Wizard live session is active, hide wizard chrome
  // and render only the step content directly
  if (state.interactiveConfig.isNavHidden) {
    const currentStep = steps[state.activeStepIndex];
    if (currentStep) {
      const StepComponent = currentStep.component;
      return (
        <StepComponent
          state={state}
          dispatch={dispatch}
          validationErrors={validationErrors}
        />
      );
    }
  }

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create/new' },
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Wizard
        i18nStrings={{
          stepNumberLabel: (stepNumber) => `Step ${stepNumber}`,
          collapsedStepsLabel: (stepNumber, stepsCount) =>
            `Step ${stepNumber} of ${stepsCount}`,
          cancelButton: 'Cancel',
          previousButton: 'Previous',
          nextButton: 'Next',
          optional: 'optional',
        }}
        submitButtonText="Create"
        isLoadingNextStep={state.isSubmitting}
        steps={wizardSteps}
        activeStepIndex={state.activeStepIndex}
        onNavigate={handleNavigate}
        onCancel={handleCancel}
        onSubmit={() => {
          setSubmitTrigger((t) => t + 1);
        }}
      />
    </SpaceBetween>
  );
}

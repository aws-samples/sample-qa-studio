import { useState, useEffect } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import SegmentedControl from "@cloudscape-design/components/segmented-control";
import Grid from "@cloudscape-design/components/grid";
import Autosuggest from "@cloudscape-design/components/autosuggest";
import Textarea from "@cloudscape-design/components/textarea";
import Input from "@cloudscape-design/components/input";
import Toggle from "@cloudscape-design/components/toggle";
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Link from "@cloudscape-design/components/link";
import Spinner from "@cloudscape-design/components/spinner";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import Checkbox from "@cloudscape-design/components/checkbox";
import Alert from "@cloudscape-design/components/alert";
import { api } from '../../utils/api';
import DateFormatSelect from './DateFormatSelect';
import DateValidationEditor from './DateValidationEditor';
import {
  buildDateOpArgs,
  loadDateOpFields,
  isDateOpValid,
  DATE_OPERATIONS,
  DURATION_UNITS,
  EPOCH_UNITS,
  type DateOpFields,
  type DateOperation,
  EMPTY_DATE_FIELDS,
} from './transformDateArgs';
import { isDateValidationValid } from './dateValidationArgs';

interface StepFormModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (stepData: any) => Promise<void>;
  onUpdateFromTemplate?: () => Promise<void>;
  step?: any; // For editing existing steps
  usecaseId: string;
  title: string;
  existingSteps?: any[]; // For runtime variable suggestions
}

const STEP_TYPE_OPTIONS = [
  { label: 'Navigation', value: 'navigation' },
  { label: 'Browser', value: 'browser' },
  { label: 'Transform', value: 'transform' },
  { label: 'Secret', value: 'secret' },
  { label: 'Validation', value: 'validation' },
  { label: 'Retrieve Value', value: 'retrieve_value' },
  { label: 'Assertion', value: 'assertion' },
  { label: 'Download', value: 'download' },
  { label: 'Network Assertion', value: 'network_assertion' }
];

const BROWSER_ACTION_OPTIONS = [
  { label: 'Reload', value: 'reload' },
  { label: 'Back', value: 'back' },
  { label: 'Forward', value: 'forward' },
  { label: 'Navigate to URL', value: 'navigate' }
];

const TRANSFORM_OPERATION_OPTIONS = [
  { label: 'Math Expression', value: 'math', description: 'Evaluate arithmetic: {{ price }} * 1.2' },
  { label: 'Round', value: 'round', description: 'Round a number to N digits' },
  { label: 'Floor', value: 'floor', description: 'Round down to nearest integer' },
  { label: 'Ceil', value: 'ceil', description: 'Round up to nearest integer' },
  { label: 'Abs', value: 'abs', description: 'Absolute value' },
  { label: 'Min', value: 'min', description: 'Minimum of a list of values' },
  { label: 'Max', value: 'max', description: 'Maximum of a list of values' },
  { label: 'Concat', value: 'concat', description: 'Concatenate strings' },
  { label: 'Upper', value: 'upper', description: 'Convert to uppercase' },
  { label: 'Lower', value: 'lower', description: 'Convert to lowercase' },
  { label: 'Trim', value: 'trim', description: 'Remove leading/trailing whitespace' },
  { label: 'Replace', value: 'replace', description: 'Replace occurrences in a string' },
  { label: 'Substring', value: 'substring', description: 'Extract part of a string' },
  { label: 'Length', value: 'length', description: 'Get string length' },
  { label: 'To Number', value: 'to_number', description: 'Convert string to number' },
  { label: 'To String', value: 'to_string', description: 'Convert to string' },
  { label: 'To Integer', value: 'to_int', description: 'Convert to integer' },
  { label: 'Regex Extract', value: 'regex_extract', description: 'Extract with a regex pattern' },
  { label: 'Format', value: 'format', description: 'Format a template string' },
  { label: 'Parse Date', value: 'parse_date', description: 'Parse a date string into canonical UTC ISO 8601' },
  { label: 'Format Date', value: 'format_date', description: 'Render a canonical date in a target strftime format' },
  { label: 'Add Duration', value: 'add_duration', description: 'Add or subtract a duration from a date' },
  { label: 'Date Diff', value: 'date_diff', description: 'Compute the signed difference between two dates' },
  { label: 'To Epoch', value: 'to_epoch', description: 'Convert a date to a Unix epoch integer' }
];
const NETWORK_METHOD_OPTIONS = [
  { label: 'Any method', value: '' },
  { label: 'GET', value: 'GET' },
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'PATCH', value: 'PATCH' },
  { label: 'DELETE', value: 'DELETE' },
  { label: 'HEAD', value: 'HEAD' },
  { label: 'OPTIONS', value: 'OPTIONS' }
];

const NETWORK_REQUEST_MATCH_TYPE_SEGMENTS = [
  { id: 'exact', text: 'Exact' },
  { id: 'subset', text: 'Subset' },
  { id: 'schema', text: 'JSON Schema' }
];

const NETWORK_RESPONSE_MATCH_TYPE_SEGMENTS = [
  { id: 'subset', text: 'Subset' },
  { id: 'schema', text: 'JSON Schema' }
];

// Body-size cap sourced from a Vite build-time env var so operators who
// raise `networkAssertionBodyMaxBytes` in `configuration.json` see the
// matching client-side counter ceiling.  Defaults to 1 MiB when unset.
// The server is authoritative — the client guard is UX courtesy.
const _envCap = Number(
  (import.meta as any).env?.VITE_NETWORK_ASSERTION_BODY_MAX_BYTES,
);
const NETWORK_BODY_BYTE_LIMIT =
  Number.isFinite(_envCap) && _envCap > 0 ? _envCap : 1_048_576;
const NETWORK_BODY_WARN_BYTES = Math.floor(NETWORK_BODY_BYTE_LIMIT * 0.86);
const NETWORK_TIMEOUT_DEFAULT = 15;
const NETWORK_TIMEOUT_MAX = 120;

const NETWORK_STATUS_MIN = 100;
const NETWORK_STATUS_MAX = 599;
const VALIDATION_TYPE_OPTIONS = [
  { label: 'Boolean (True/False)', value: 'bool' },
  { label: 'String Comparison', value: 'string' },
  { label: 'Number Comparison', value: 'number' },
  { label: 'Date Comparison', value: 'date' }
];

const VALUE_TYPE_OPTIONS = [
  { label: 'String', value: 'string' },
  { label: 'Number', value: 'number' },
  { label: 'Boolean', value: 'bool' },
  { label: 'Date', value: 'date' }
];

const VALIDATION_OPERATOR_OPTIONS = {
  string: [
    { label: 'Exact Match', value: 'exact' },
    { label: 'Exact Match (Case Insensitive)', value: 'exact_case_insensitive' },
    { label: 'Not Equal', value: 'not_equal' },
    { label: 'Contains', value: 'contains' },
    { label: 'Contains (Case Insensitive)', value: 'contains_case_insensitive' }
  ],
  number: [
    { label: 'Equals', value: 'equals' },
    { label: 'Less Than', value: 'less_then' },
    { label: 'Greater Than', value: 'greater_then' },
    { label: 'Greater or Equal Than', value: 'greater_or_equal_then' },
    { label: 'Less or Equal Than', value: 'less_or_equal_then' }
  ]
};

const BOOLEAN_OPTIONS = [
  { label: 'True', value: 'true' },
  { label: 'False', value: 'false' },
  { label: 'Use Variable', value: 'variable' }
];



export default function StepFormModal({
  visible,
  onDismiss,
  onSubmit,
  onUpdateFromTemplate,
  step,
  usecaseId,
  title,
  existingSteps = []
}: StepFormModalProps) {
  const [stepType, setStepType] = useState('navigation');
  const [stepTypeInputValue, setStepTypeInputValue] = useState(
    STEP_TYPE_OPTIONS.find(opt => opt.value === 'navigation')?.label || ''
  );
  const [instruction, setInstruction] = useState('');
  const [selectedSecret, setSelectedSecret] = useState('');
  const [validationType, setValidationType] = useState('bool');
  const [validationOperator, setValidationOperator] = useState('exact');
  const [validationValue, setValidationValue] = useState('');
  const [availableSecrets, setAvailableSecrets] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [captureVariable, setCaptureVariable] = useState('');
  const [valueType, setValueType] = useState('string');
  const [valueFormat, setValueFormat] = useState('');
  const [valueSource, setValueSource] = useState('screen');
  const [assertionVariable, setAssertionVariable] = useState('');
  const [booleanInputMode, setBooleanInputMode] = useState('true');
  const [updatingFromTemplate, setUpdatingFromTemplate] = useState(false);
  // Browser step state
  const [browserAction, setBrowserAction] = useState('reload');
  const [browserHardReload, setBrowserHardReload] = useState(false);
  const [browserNavigateUrl, setBrowserNavigateUrl] = useState('');
  // Transform step state
  const [transformOperation, setTransformOperation] = useState('math');
  const [transformExpression, setTransformExpression] = useState('');
  const [transformValue, setTransformValue] = useState('');
  const [transformOld, setTransformOld] = useState('');
  const [transformNew, setTransformNew] = useState('');
  const [transformStart, setTransformStart] = useState('0');
  const [transformEnd, setTransformEnd] = useState('');
  const [transformPattern, setTransformPattern] = useState('');
  const [transformGroup, setTransformGroup] = useState('0');
  const [transformDigits, setTransformDigits] = useState('0');
  const [transformTemplate, setTransformTemplate] = useState('');
  const [transformFormatArgs, setTransformFormatArgs] = useState('');
  const [transformValues, setTransformValues] = useState('');
  // Date transform state — see transformDateArgs.ts for the field shape.
  const [transformDateFields, setTransformDateFields] = useState<DateOpFields>(EMPTY_DATE_FIELDS);
  const [templateStep, setTemplateStep] = useState<any>(null);
  const [loadingTemplateStep, setLoadingTemplateStep] = useState(false);
  const [templateDifferences, setTemplateDifferences] = useState<Array<{field: string, current: any, template: any}>>([]);
  const [enableAdvancedClickTypes, setEnableAdvancedClickTypes] = useState(false);

  // network_assertion step fields
  const [networkUrlPattern, setNetworkUrlPattern] = useState('');

  // Inline secret creation
  const [showCreateSecret, setShowCreateSecret] = useState(false);
  const [newSecretKey, setNewSecretKey] = useState('');
  const [newSecretValue, setNewSecretValue] = useState('');
  const [creatingSecret, setCreatingSecret] = useState(false);
  const [createSecretError, setCreateSecretError] = useState<string | null>(null);
  const [networkMethod, setNetworkMethod] = useState('');
  const [networkRequestBody, setNetworkRequestBody] = useState('');
  const [networkBodyMatchType, setNetworkBodyMatchType] = useState('exact');
  const [networkMockResponse, setNetworkMockResponse] = useState('');
  const [networkMockPassthrough, setNetworkMockPassthrough] = useState(false);
  const [networkTimeout, setNetworkTimeout] = useState<string>(String(NETWORK_TIMEOUT_DEFAULT));
  // Response-side assertion fields
  const [networkResponseStatus, setNetworkResponseStatus] = useState<string>('');
  const [networkResponseBody, setNetworkResponseBody] = useState('');
  const [networkResponseBodyMatchType, setNetworkResponseBodyMatchType] = useState('subset');

  // Get available runtime variables from existing retrieve_value steps
  const getAvailableRuntimeVariables = () => {
    return existingSteps
      .filter(step => (step.step_type === 'retrieve_value' || step.step_type === 'transform') && step.capture_variable)
      .map(step => ({
        label: step.capture_variable,
        value: step.capture_variable,
        description: `From step ${step.sort}: ${step.instruction || step.transform_operation || ''}`
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  };

  // Initialize form with step data for editing
  useEffect(() => {
    if (step) {
      setStepType(step.step_type || 'navigation');
      setStepTypeInputValue(
        STEP_TYPE_OPTIONS.find(opt => opt.value === (step.step_type || 'navigation'))?.label || ''
      );
      setInstruction(step.instruction || '');
      setSelectedSecret(step.secret_key || '');
      setValidationType(step.validation_type || 'bool');
      setValidationOperator(step.validation_operator || 'exact');
      setValidationValue(step.validation_value || '');
      setCaptureVariable(step.capture_variable || '');
      setValueType(step.value_type || 'string');
      setValueFormat(step.value_format || '');
      setValueSource(step.value_source || 'screen');
      setAssertionVariable(step.assertion_variable || '');
      setEnableAdvancedClickTypes(step.enable_advanced_click_types || false);
      // Initialize browser step fields
      if (step.browser_action) setBrowserAction(step.browser_action);
      if (step.browser_args) {
        try {
          const args = JSON.parse(step.browser_args);
          setBrowserHardReload(args.hard || false);
          setBrowserNavigateUrl(args.url || '');
        } catch {}
      }
      // Initialize transform step fields
      if (step.transform_operation) setTransformOperation(step.transform_operation);
      if (step.transform_args) {
        try {
          const args = JSON.parse(step.transform_args);
          setTransformExpression(args.expression || '');
          setTransformValue(args.value != null ? String(args.value) : '');
          setTransformOld(args.old || '');
          setTransformNew(args.new || '');
          setTransformStart(args.start != null ? String(args.start) : '0');
          setTransformEnd(args.end != null ? String(args.end) : '');
          setTransformPattern(args.pattern || '');
          setTransformGroup(args.group != null ? String(args.group) : '0');
          setTransformDigits(args.digits != null ? String(args.digits) : '0');
          setTransformTemplate(args.template || '');
          setTransformFormatArgs((args.args || []).join(', '));
          setTransformValues((args.values || []).join(', '));
          if (DATE_OPERATIONS.has(step.transform_operation as DateOperation)) {
            setTransformDateFields(loadDateOpFields(step.transform_operation as DateOperation, args));
          } else {
            setTransformDateFields(EMPTY_DATE_FIELDS);
          }
        } catch {}
      }
      setNetworkUrlPattern(step.network_url_pattern || '');
      setNetworkMethod(step.network_method || '');
      setNetworkRequestBody(step.network_request_body || '');
      setNetworkBodyMatchType(step.network_body_match_type || 'exact');
      setNetworkMockResponse(step.network_mock_response || '');
      setNetworkMockPassthrough(Boolean(step.network_mock_passthrough));
      setNetworkTimeout(
        step.network_timeout != null ? String(step.network_timeout) : String(NETWORK_TIMEOUT_DEFAULT)
      );
      setNetworkResponseStatus(
        step.network_response_status != null ? String(step.network_response_status) : ''
      );
      setNetworkResponseBody(step.network_response_body || '');
      setNetworkResponseBodyMatchType(step.network_response_body_match_type || 'subset');
      // Initialize boolean input mode based on existing value
      if (step.validation_value && (step.validation_value === 'true' || step.validation_value === 'false')) {
        setBooleanInputMode(step.validation_value);
      } else if (step.validation_value && step.validation_value.includes('{{')) {
        setBooleanInputMode('variable');
      } else {
        setBooleanInputMode('true');
      }
    } else {
      // Reset form for new step
      setStepType('navigation');
      setStepTypeInputValue(
        STEP_TYPE_OPTIONS.find(opt => opt.value === 'navigation')?.label || ''
      );
      setInstruction('');
      setSelectedSecret('');
      setValidationType('bool');
      setValidationOperator('exact');
      setValidationValue('');
      setCaptureVariable('');
      setValueType('string');
      setValueFormat('');
      setValueSource('screen');
      setAssertionVariable('');
      setBooleanInputMode('true');
      setEnableAdvancedClickTypes(false);
      setBrowserAction('reload');
      setBrowserHardReload(false);
      setBrowserNavigateUrl('');
      setTransformOperation('math');
      setTransformExpression('');
      setTransformValue('');
      setTransformOld('');
      setTransformNew('');
      setTransformStart('0');
      setTransformEnd('');
      setTransformPattern('');
      setTransformGroup('0');
      setTransformDigits('0');
      setTransformTemplate('');
      setTransformFormatArgs('');
      setTransformValues('');
      setTransformDateFields(EMPTY_DATE_FIELDS);
      setNetworkUrlPattern('');
      setNetworkMethod('');
      setNetworkRequestBody('');
      setNetworkBodyMatchType('exact');
      setNetworkMockResponse('');
      setNetworkMockPassthrough(false);
      setNetworkTimeout(String(NETWORK_TIMEOUT_DEFAULT));
      setNetworkResponseStatus('');
      setNetworkResponseBody('');
      setNetworkResponseBodyMatchType('subset');
      setShowCreateSecret(false);
      setNewSecretKey('');
      setNewSecretValue('');
      setCreateSecretError(null);
    }
  }, [step]);

  // Load available secrets when modal opens or step type changes to secret
  useEffect(() => {
    if (visible && stepType === 'secret') {
      loadSecrets();
    }
  }, [visible, stepType, usecaseId]);

  // Load template step data when modal opens with a step from a template
  useEffect(() => {
    if (visible && step?.template_id && step?.template_step_id) {
      loadTemplateStep();
    } else {
      setTemplateStep(null);
      setTemplateDifferences([]);
    }
  }, [visible, step?.template_id, step?.template_step_id]);

  const loadSecrets = async () => {
    try {
      const response = await api.get(`usecase/${usecaseId}/secrets`);
      setAvailableSecrets(response.secrets || []);
    } catch (error) {
      console.error('Failed to load secrets:', error);
      setAvailableSecrets([]);
    }
  };

  const handleCreateSecret = async () => {
    const key = newSecretKey.trim();
    const value = newSecretValue.trim();
    if (!key || !value) {
      setCreateSecretError('Both key and value are required');
      return;
    }
    if (availableSecrets.some(s => s.key === key)) {
      setCreateSecretError(`Secret "${key}" already exists`);
      return;
    }

    setCreatingSecret(true);
    setCreateSecretError(null);
    try {
      await api.post(`usecase/${usecaseId}/secrets`, { secrets: [{ key, value }] });
      await loadSecrets();
      setSelectedSecret(key);
      setNewSecretKey('');
      setNewSecretValue('');
      setShowCreateSecret(false);
    } catch (error) {
      console.error('Failed to create secret:', error);
      setCreateSecretError('Failed to create secret');
    } finally {
      setCreatingSecret(false);
    }
  };

  const loadTemplateStep = async () => {
    if (!step?.template_id || !step?.template_step_id) return;
    
    setLoadingTemplateStep(true);
    try {
      const response = await api.get(`templates/${step.template_id}/steps`);
      const steps = response.steps || [];
      const matchingStep = steps.find((s: any) => s.id === step.template_step_id);
      
      if (matchingStep) {
        setTemplateStep(matchingStep);
        calculateDifferences(step, matchingStep);
      }
    } catch (error) {
      console.error('Failed to load template step:', error);
      setTemplateStep(null);
    } finally {
      setLoadingTemplateStep(false);
    }
  };

  const calculateDifferences = (currentStep: any, templateStep: any) => {
    const diffs: Array<{field: string, current: any, template: any}> = [];
    
    // Helper to check if a value is empty (null, undefined, or empty string)
    const isEmpty = (val: any) => val === null || val === undefined || val === '';
    
    // Helper to check if values are different (ignoring empty values on both sides)
    const isDifferent = (current: any, template: any) => {
      const currentEmpty = isEmpty(current);
      const templateEmpty = isEmpty(template);
      
      // If both are empty, they're not different
      if (currentEmpty && templateEmpty) return false;
      
      // If one is empty and the other isn't, they're different
      if (currentEmpty !== templateEmpty) return true;
      
      // Compare actual values
      return current !== template;
    };
    
    // Always compare instruction and step_type
    if (isDifferent(currentStep.instruction, templateStep.instruction)) {
      diffs.push({
        field: 'Instruction',
        current: currentStep.instruction || '(empty)',
        template: templateStep.instruction || '(empty)'
      });
    }
    if (isDifferent(currentStep.step_type, templateStep.step_type)) {
      diffs.push({
        field: 'Step Type',
        current: currentStep.step_type || '(empty)',
        template: templateStep.step_type || '(empty)'
      });
    }
    
    // Only compare step-type-specific fields
    const stepType = templateStep.step_type || currentStep.step_type;
    
    if (stepType === 'secret' && isDifferent(currentStep.secret_key, templateStep.secret_key)) {
      diffs.push({
        field: 'Secret Key',
        current: currentStep.secret_key || '(empty)',
        template: templateStep.secret_key || '(empty)'
      });
    }
    
    if (stepType === 'retrieve_value') {
      if (isDifferent(currentStep.capture_variable, templateStep.capture_variable)) {
        diffs.push({
          field: 'Capture Variable',
          current: currentStep.capture_variable || '(empty)',
          template: templateStep.capture_variable || '(empty)'
        });
      }
      if (isDifferent(currentStep.value_type, templateStep.value_type)) {
        diffs.push({
          field: 'Value Type',
          current: currentStep.value_type || '(empty)',
          template: templateStep.value_type || '(empty)'
        });
      }
    }
    
    if (stepType === 'validation' || stepType === 'assertion') {
      if (isDifferent(currentStep.validation_type, templateStep.validation_type)) {
        diffs.push({
          field: 'Validation Type',
          current: currentStep.validation_type || '(empty)',
          template: templateStep.validation_type || '(empty)'
        });
      }
      if (isDifferent(currentStep.validation_operator, templateStep.validation_operator)) {
        diffs.push({
          field: 'Validation Operator',
          current: currentStep.validation_operator || '(empty)',
          template: templateStep.validation_operator || '(empty)'
        });
      }
      if (isDifferent(currentStep.validation_value, templateStep.validation_value)) {
        diffs.push({
          field: 'Validation Value',
          current: currentStep.validation_value || '(empty)',
          template: templateStep.validation_value || '(empty)'
        });
      }
    }
    
    if (stepType === 'assertion' && isDifferent(currentStep.assertion_variable, templateStep.assertion_variable)) {
      diffs.push({
        field: 'Assertion Variable',
        current: currentStep.assertion_variable || '(empty)',
        template: templateStep.assertion_variable || '(empty)'
      });
    }
    
    setTemplateDifferences(diffs);
  };

  const buildTransformArgs = (): Record<string, any> => {
    if (DATE_OPERATIONS.has(transformOperation as DateOperation)) {
      return buildDateOpArgs(transformOperation as DateOperation, transformDateFields);
    }
    switch (transformOperation) {
      case 'math': return { expression: transformExpression.trim() };
      case 'round': return { value: transformValue.trim(), digits: parseInt(transformDigits) || 0 };
      case 'floor': case 'ceil': case 'abs':
      case 'upper': case 'lower': case 'trim': case 'length':
      case 'to_number': case 'to_string': case 'to_int':
        return { value: transformValue.trim() };
      case 'replace': return { value: transformValue.trim(), old: transformOld, new: transformNew };
      case 'substring': {
        const args: any = { value: transformValue.trim(), start: parseInt(transformStart) || 0 };
        if (transformEnd.trim()) args.end = parseInt(transformEnd);
        return args;
      }
      case 'regex_extract': return { value: transformValue.trim(), pattern: transformPattern, group: parseInt(transformGroup) || 0 };
      case 'format': return { template: transformTemplate.trim(), args: transformFormatArgs.split(',').map(s => s.trim()).filter(Boolean) };
      case 'concat': return { values: transformValues.split(',').map(s => s.trim()) };
      case 'min': case 'max': return { values: transformValues.split(',').map(s => s.trim()) };
      default: return {};
    }
  };

  const handleSubmit = async () => {
    if (stepType === 'browser' && browserAction === 'navigate' && !browserNavigateUrl.trim()) return;
    if (stepType === 'transform' && !captureVariable.trim()) return;
    if (stepType !== 'assertion' && stepType !== 'browser' && stepType !== 'transform' && !instruction.trim()) return;
    if (stepType === 'secret' && !selectedSecret) return;
    if (stepType === 'validation' && validationType === 'string' && !validationValue.trim()) return;
    if (stepType === 'validation' && validationType === 'number' && !validationValue.trim()) return;
    if (stepType === 'validation' && validationType === 'bool' && !validationValue.trim()) return;
    if (stepType === 'retrieve_value' && !captureVariable.trim()) return;
    if (stepType === 'assertion' && !assertionVariable.trim()) return;
    if (stepType === 'assertion' && validationType === 'string' && !validationValue.trim()) return;
    if (stepType === 'assertion' && validationType === 'number' && !validationValue.trim()) return;
    if (stepType === 'assertion' && validationType === 'bool' && !validationValue.trim()) return;
    if ((stepType === 'validation' || stepType === 'assertion') && validationType === 'date'
        && !isDateValidationValid(validationOperator, validationValue)) return;

    setSaving(true);
    try {
      const stepData: any = {
        instruction: stepType === 'assertion' ? (instruction.trim() || 'Assertion step')
          : stepType === 'browser' ? (instruction.trim() || `Browser ${browserAction}`)
          : stepType === 'transform' ? (instruction.trim() || `Transform ${transformOperation}`)
          : instruction.trim(),
        step_type: stepType
      };

      // Add advanced click types flag for navigation steps
      if (stepType === 'navigation') {
        stepData.enable_advanced_click_types = enableAdvancedClickTypes;
      }

      if (stepType === 'browser') {
        stepData.browser_action = browserAction;
        const args: any = {};
        if (browserAction === 'reload' && browserHardReload) args.hard = true;
        if (browserAction === 'navigate') args.url = browserNavigateUrl.trim();
        stepData.browser_args = JSON.stringify(args);
      } else if (stepType === 'transform') {
        stepData.transform_operation = transformOperation;
        stepData.capture_variable = captureVariable.trim();
        stepData.transform_args = JSON.stringify(buildTransformArgs());
      } else if (stepType === 'secret') {
        stepData.secret_key = selectedSecret;
      } else if (stepType === 'validation') {
        stepData.validation_type = validationType;
        stepData.validation_operator = validationOperator;
        stepData.validation_value = validationValue.trim();
        stepData.operator = validationOperator;
      } else if (stepType === 'retrieve_value') {
        stepData.capture_variable = captureVariable.trim();
        stepData.value_type = valueType;
        stepData.value_source = valueSource;
        if (valueType === 'date') {
          stepData.value_format = valueFormat;
        }
      } else if (stepType === 'assertion') {
        stepData.assertion_variable = assertionVariable.trim();
        stepData.validation_type = validationType;
        stepData.validation_operator = validationOperator;
        stepData.validation_value = validationValue.trim();
      } else if (stepType === 'network_assertion') {
        stepData.network_url_pattern = networkUrlPattern.trim();
        if (networkMethod) {
          stepData.network_method = networkMethod;
        }
        if (networkRequestBody.trim()) {
          stepData.network_request_body = networkRequestBody.trim();
          stepData.network_body_match_type = networkBodyMatchType;
        }
        if (networkMockResponse.trim()) {
          stepData.network_mock_response = networkMockResponse.trim();
          stepData.network_mock_passthrough = networkMockPassthrough;
        }
        const parsedTimeout = parseInt(networkTimeout, 10);
        if (!Number.isNaN(parsedTimeout)) {
          stepData.network_timeout = parsedTimeout;
        }
        // Response-side assertion — only send fields the user filled in.
        const parsedStatus = parseInt(networkResponseStatus, 10);
        if (!Number.isNaN(parsedStatus)) {
          stepData.network_response_status = parsedStatus;
        }
        if (networkResponseBody.trim()) {
          stepData.network_response_body = networkResponseBody.trim();
          stepData.network_response_body_match_type = networkResponseBodyMatchType;
        }
      }

      // Ensure other step types don't have these fields
      if (stepType !== 'retrieve_value' && stepType !== 'transform') {
        stepData.capture_variable = '';
        stepData.value_type = '';
      }

      await onSubmit(stepData);
      onDismiss();
    } catch (error) {
      console.error('Failed to save step:', error);
    } finally {
      setSaving(false);
    }
  };

  const isFormValid = () => {
    if (stepType === 'browser') {
      if (browserAction === 'navigate' && !browserNavigateUrl.trim()) return false;
      return true;
    }
    if (stepType === 'transform') {
      if (!captureVariable.trim()) return false;
      if (DATE_OPERATIONS.has(transformOperation as DateOperation)) {
        return isDateOpValid(transformOperation as DateOperation, transformDateFields);
      }
      if (transformOperation === 'math' && !transformExpression.trim()) return false;
      if (['floor', 'ceil', 'abs', 'upper', 'lower', 'trim', 'length', 'to_number', 'to_string', 'to_int'].includes(transformOperation) && !transformValue.trim()) return false;
      if (transformOperation === 'round' && !transformValue.trim()) return false;
      if (transformOperation === 'replace' && !transformValue.trim()) return false;
      if (transformOperation === 'substring' && !transformValue.trim()) return false;
      if (transformOperation === 'regex_extract' && (!transformValue.trim() || !transformPattern.trim())) return false;
      if (transformOperation === 'format' && !transformTemplate.trim()) return false;
      if (['concat', 'min', 'max'].includes(transformOperation) && !transformValues.trim()) return false;
      return true;
    }
    if (stepType !== 'assertion' && !instruction.trim()) return false;
    if (stepType === 'secret' && !selectedSecret) return false;
    if (stepType === 'validation' && validationType === 'string' && !validationValue.trim()) return false;
    if (stepType === 'validation' && validationType === 'number' && !validationValue.trim()) return false;
    if (stepType === 'validation' && validationType === 'bool' && !validationValue.trim()) return false;
    if (stepType === 'retrieve_value' && !captureVariable.trim()) return false;
    if (stepType === 'assertion' && !assertionVariable.trim()) return false;
    if (stepType === 'assertion' && validationType === 'string' && !validationValue.trim()) return false;
    if (stepType === 'assertion' && validationType === 'number' && !validationValue.trim()) return false;
    if (stepType === 'assertion' && validationType === 'bool' && !validationValue.trim()) return false;
    if ((stepType === 'validation' || stepType === 'assertion') && validationType === 'date'
        && !isDateValidationValid(validationOperator, validationValue)) return false;
    if (stepType === 'network_assertion') {
      if (!networkUrlPattern.trim()) return false;
      // Size cap — counted as UTF-8 bytes to match server-side check.
      const bodyBytes = new TextEncoder().encode(networkRequestBody).length;
      const mockBytes = new TextEncoder().encode(networkMockResponse).length;
      const respBytes = new TextEncoder().encode(networkResponseBody).length;
      if (
        bodyBytes > NETWORK_BODY_BYTE_LIMIT ||
        mockBytes > NETWORK_BODY_BYTE_LIMIT ||
        respBytes > NETWORK_BODY_BYTE_LIMIT
      ) return false;
      const parsedTimeout = parseInt(networkTimeout, 10);
      if (Number.isNaN(parsedTimeout) || parsedTimeout < 1 || parsedTimeout > NETWORK_TIMEOUT_MAX) return false;
      // Response status is optional, but if set, must be in [100, 599].
      if (networkResponseStatus.trim()) {
        const parsedStatus = parseInt(networkResponseStatus, 10);
        if (
          Number.isNaN(parsedStatus) ||
          parsedStatus < NETWORK_STATUS_MIN ||
          parsedStatus > NETWORK_STATUS_MAX
        ) return false;
      }
    }
    return true;
  };

  const handleUpdateFromTemplate = async () => {
    if (!onUpdateFromTemplate) return;
    
    setUpdatingFromTemplate(true);
    try {
      await onUpdateFromTemplate();
      onDismiss();
    } catch (error) {
      console.error('Failed to update from template:', error);
    } finally {
      setUpdatingFromTemplate(false);
    }
  };

  return (
    <Modal
      onDismiss={onDismiss}
      visible={visible}
      closeAriaLabel="Close modal"
      size="large"
      header={title}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss} disabled={saving || updatingFromTemplate}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={saving}
              disabled={!isFormValid() || saving || updatingFromTemplate}
            >
              {step ? 'Update Step' : 'Create Step'}
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        <FormField
          stretch
          label="Step Type"
          description="Select the type of step to create"
        >
          <Autosuggest
            value={stepTypeInputValue}
            onChange={({ detail }) => {
              setStepTypeInputValue(detail.value);
            }}
            onSelect={({ detail }) => {
              const match = STEP_TYPE_OPTIONS.find(opt => opt.value === detail.value);
              if (match) {
                setStepType(match.value);
                setStepTypeInputValue(match.label);
                // Reset all dependent fields when changing type
                setSelectedSecret('');
                setValidationType('bool');
                setValidationOperator('exact');
                setValidationValue('');
                setCaptureVariable('');
                setValueType('string');
              }
            }}
            options={step?.step_type === 'url' ? [...STEP_TYPE_OPTIONS, { label: 'URL (deprecated — use Browser → Navigate)', value: 'url' }] : STEP_TYPE_OPTIONS}
            options={STEP_TYPE_OPTIONS}
            enteredTextLabel={(value) => `Use: "${value}"`}
            placeholder="Search step types..."
            empty="No matching step type"
          />
        </FormField>

        {stepType !== 'assertion' && stepType !== 'browser' && stepType !== 'transform' && (
          <FormField
            stretch
            label="Instruction"
            description={
              stepType === 'navigation' ? 'Describe the action to perform on the page' :
                stepType === 'url' ? 'Enter the URL to navigate to (e.g., "https://example.com/login")' :
                  stepType === 'secret' ? 'Describe the action (e.g., "Type password in login field")' :
                    stepType === 'validation' ? 'Describe what should be validated on the page' :
                      stepType === 'download' ? 'Describe the action that triggers the download. Automatically handles downloads in popups or current page.' :
                        'Describe what value to retrieve from the page'
            }
          >
            <Textarea
              value={instruction}
              onChange={({ detail }) => setInstruction(detail.value)}
              placeholder={
                stepType === 'navigation' ? 'Enter navigation instruction' :
                  stepType === 'url' ? 'https://example.com/page' :
                    stepType === 'secret' ? 'Describe the action with the secret' :
                      stepType === 'validation' ? 'Describe the validation to perform' :
                        stepType === 'download' ? 'Click the download button' :
                            'Describe what to retrieve (e.g., "Get the product price")'
              }
              rows={3}
            />
          </FormField>
        )}

        {stepType === 'navigation' && (
          <Checkbox
            checked={enableAdvancedClickTypes}
            onChange={({ detail }) => setEnableAdvancedClickTypes(detail.checked)}
          >
            Enable advanced click types (double-click, right-click)
          </Checkbox>
        )}

        {stepType === 'browser' && (
          <>
            <FormField label="Browser Action" stretch>
              <Select
                selectedOption={BROWSER_ACTION_OPTIONS.find(opt => opt.value === browserAction) || null}
                onChange={({ detail }) => setBrowserAction(detail.selectedOption?.value || 'reload')}
                options={BROWSER_ACTION_OPTIONS}
              />
            </FormField>
            {browserAction === 'reload' && (
              <Checkbox
                checked={browserHardReload}
                onChange={({ detail }) => setBrowserHardReload(detail.checked)}
              >
                Hard reload (bypass cache)
              </Checkbox>
            )}
            {browserAction === 'navigate' && (
              <FormField label="URL" stretch description="Enter the URL to navigate to">
                <Input
                  value={browserNavigateUrl}
                  onChange={({ detail }) => setBrowserNavigateUrl(detail.value)}
                  placeholder="https://example.com/page"
                />
              </FormField>
            )}
          </>
        )}

        {stepType === 'transform' && (
          <>
            <FormField label="Operation" stretch>
              <Select
                selectedOption={TRANSFORM_OPERATION_OPTIONS.find(opt => opt.value === transformOperation) || null}
                onChange={({ detail }) => setTransformOperation(detail.selectedOption?.value || 'math')}
                options={TRANSFORM_OPERATION_OPTIONS}
              />
            </FormField>
            <FormField label="Output Variable Name" stretch description="The result will be stored in this variable (use with {{ variable_name }})">
              <Input
                value={captureVariable}
                onChange={({ detail }) => setCaptureVariable(detail.value)}
                placeholder="result_variable"
              />
            </FormField>
            {transformOperation === 'math' && (
              <FormField label="Expression" stretch description="Arithmetic expression. Use {{ variable }} to reference captured values.">
                <Textarea
                  value={transformExpression}
                  onChange={({ detail }) => setTransformExpression(detail.value)}
                  placeholder="{{ price }} * {{ quantity }} + 5.99"
                  rows={2}
                />
              </FormField>
            )}
            {['floor', 'ceil', 'abs', 'upper', 'lower', 'trim', 'length', 'to_number', 'to_string', 'to_int'].includes(transformOperation) && (
              <FormField label="Value" stretch description="Input value. Use {{ variable }} to reference captured values.">
                <Input
                  value={transformValue}
                  onChange={({ detail }) => setTransformValue(detail.value)}
                  placeholder="{{ captured_value }}"
                />
              </FormField>
            )}
            {transformOperation === 'round' && (
              <>
                <FormField label="Value" stretch>
                  <Input value={transformValue} onChange={({ detail }) => setTransformValue(detail.value)} placeholder="{{ price }}" />
                </FormField>
                <FormField label="Decimal Digits" stretch>
                  <Input value={transformDigits} onChange={({ detail }) => setTransformDigits(detail.value)} placeholder="2" type="number" />
                </FormField>
              </>
            )}
            {transformOperation === 'replace' && (
              <>
                <FormField label="Value" stretch>
                  <Input value={transformValue} onChange={({ detail }) => setTransformValue(detail.value)} placeholder="{{ text }}" />
                </FormField>
                <FormField label="Find" stretch>
                  <Input value={transformOld} onChange={({ detail }) => setTransformOld(detail.value)} placeholder="old text" />
                </FormField>
                <FormField label="Replace With" stretch>
                  <Input value={transformNew} onChange={({ detail }) => setTransformNew(detail.value)} placeholder="new text" />
                </FormField>
              </>
            )}
            {transformOperation === 'substring' && (
              <>
                <FormField label="Value" stretch>
                  <Input value={transformValue} onChange={({ detail }) => setTransformValue(detail.value)} placeholder="{{ text }}" />
                </FormField>
                <FormField label="Start Index" stretch>
                  <Input value={transformStart} onChange={({ detail }) => setTransformStart(detail.value)} placeholder="0" type="number" />
                </FormField>
                <FormField label="End Index (optional)" stretch>
                  <Input value={transformEnd} onChange={({ detail }) => setTransformEnd(detail.value)} placeholder="5" type="number" />
                </FormField>
              </>
            )}
            {transformOperation === 'regex_extract' && (
              <>
                <FormField label="Value" stretch>
                  <Input value={transformValue} onChange={({ detail }) => setTransformValue(detail.value)} placeholder="{{ text }}" />
                </FormField>
                <FormField label="Regex Pattern" stretch>
                  <Input value={transformPattern} onChange={({ detail }) => setTransformPattern(detail.value)} placeholder="#(\d+)" />
                </FormField>
                <FormField label="Capture Group" stretch>
                  <Input value={transformGroup} onChange={({ detail }) => setTransformGroup(detail.value)} placeholder="0" type="number" />
                </FormField>
              </>
            )}
            {transformOperation === 'format' && (
              <>
                <FormField label="Template" stretch description="Use {} as placeholders">
                  <Input value={transformTemplate} onChange={({ detail }) => setTransformTemplate(detail.value)} placeholder="Order #{} - {}" />
                </FormField>
                <FormField label="Arguments (comma-separated)" stretch>
                  <Input value={transformFormatArgs} onChange={({ detail }) => setTransformFormatArgs(detail.value)} placeholder="{{ order_id }}, {{ status }}" />
                </FormField>
              </>
            )}
            {['concat', 'min', 'max'].includes(transformOperation) && (
              <FormField label="Values (comma-separated)" stretch description="Use {{ variable }} to reference captured values.">
                <Input
                  value={transformValues}
                  onChange={({ detail }) => setTransformValues(detail.value)}
                  placeholder={transformOperation === 'concat' ? '{{ first_name }},  , {{ last_name }}' : '{{ price1 }}, {{ price2 }}, {{ price3 }}'}
                />
              </FormField>
            )}
            {transformOperation === 'parse_date' && (
              <>
                <FormField label="Value" stretch description="Date string to parse. Use {{ variable }} to reference captured values.">
                  <Input
                    value={transformDateFields.primary}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, primary: detail.value }))}
                    placeholder="{{ order_date }}"
                  />
                </FormField>
                <DateFormatSelect
                  value={transformDateFields.format}
                  onChange={(format) => setTransformDateFields(f => ({ ...f, format }))}
                />
              </>
            )}
            {transformOperation === 'format_date' && (
              <>
                <FormField label="Canonical Date" stretch description="ISO 8601 date string. Use parse_date first if your value isn't canonical.">
                  <Input
                    value={transformDateFields.primary}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, primary: detail.value }))}
                    placeholder="{{ order_date_iso }}"
                  />
                </FormField>
                <DateFormatSelect
                  value={transformDateFields.format}
                  onChange={(format) => setTransformDateFields(f => ({ ...f, format }))}
                  disableAutoDetect
                  label="Output Format"
                />
              </>
            )}
            {transformOperation === 'add_duration' && (
              <>
                <FormField label="Canonical Date" stretch description="ISO 8601 date string.">
                  <Input
                    value={transformDateFields.primary}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, primary: detail.value }))}
                    placeholder="{{ start_date }}"
                  />
                </FormField>
                <FormField label="Amount" stretch description="Signed integer. Negative values subtract.">
                  <Input
                    value={transformDateFields.amount}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, amount: detail.value }))}
                    placeholder="30"
                    type="number"
                  />
                </FormField>
                <FormField label="Unit" stretch description="Months and years are not supported in v1 — their arithmetic is policy-dependent.">
                  <Select
                    selectedOption={transformDateFields.unit ? { label: transformDateFields.unit, value: transformDateFields.unit } : null}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, unit: detail.selectedOption?.value || '' }))}
                    options={DURATION_UNITS.map(u => ({ label: u, value: u }))}
                    placeholder="Select a unit"
                  />
                </FormField>
              </>
            )}
            {transformOperation === 'date_diff' && (
              <>
                <FormField label="Date A" stretch description="ISO 8601 date string. The difference is computed as A − B.">
                  <Input
                    value={transformDateFields.primary}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, primary: detail.value }))}
                    placeholder="{{ end_date }}"
                  />
                </FormField>
                <FormField label="Date B" stretch description="ISO 8601 date string.">
                  <Input
                    value={transformDateFields.secondary}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, secondary: detail.value }))}
                    placeholder="{{ start_date }}"
                  />
                </FormField>
                <FormField label="Unit" stretch description="Result is the difference in this unit, truncated toward zero.">
                  <Select
                    selectedOption={transformDateFields.unit ? { label: transformDateFields.unit, value: transformDateFields.unit } : null}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, unit: detail.selectedOption?.value || '' }))}
                    options={DURATION_UNITS.map(u => ({ label: u, value: u }))}
                    placeholder="Select a unit"
                  />
                </FormField>
              </>
            )}
            {transformOperation === 'to_epoch' && (
              <>
                <FormField label="Value" stretch description="Date string. Auto-detected as ISO or epoch — use parse_date first if the value isn't canonical.">
                  <Input
                    value={transformDateFields.primary}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, primary: detail.value }))}
                    placeholder="{{ order_date_iso }}"
                  />
                </FormField>
                <FormField label="Unit" stretch description="Use seconds for compatibility with the existing number assertion operators.">
                  <Select
                    selectedOption={transformDateFields.unit ? { label: transformDateFields.unit, value: transformDateFields.unit } : null}
                    onChange={({ detail }) => setTransformDateFields(f => ({ ...f, unit: detail.selectedOption?.value || '' }))}
                    options={EPOCH_UNITS.map(u => ({ label: u, value: u }))}
                    placeholder="seconds"
                  />
                </FormField>
              </>
            )}
          </>
        )}

        {stepType === 'secret' && (
          <SpaceBetween direction="vertical" size="m">
            <FormField
              stretch
              label="Select Secret"
              description="Choose which secret to use for this step"
              secondaryControl={
                <Button
                  iconName={showCreateSecret ? "close" : "add-plus"}
                  variant="normal"
                  onClick={() => {
                    setShowCreateSecret(!showCreateSecret);
                    setCreateSecretError(null);
                  }}
                >
                  {showCreateSecret ? "Cancel" : "Add Secret"}
                </Button>
              }
            >
              <Select
                selectedOption={availableSecrets.find(secret => secret.key === selectedSecret) ?
                  { label: availableSecrets.find(secret => secret.key === selectedSecret)?.key || '', value: selectedSecret } :
                  null
                }
                onChange={({ detail }) => setSelectedSecret(detail.selectedOption?.value || '')}
                options={availableSecrets.map(secret => ({
                  label: secret.key,
                  value: secret.key,
                  description: secret.description
                }))}
                placeholder="Select a secret"
                empty="No secrets available. Click + to create one."
              />
            </FormField>

            {showCreateSecret && (
              <Container header={<Header variant="h3">Create Secret</Header>}>
                <SpaceBetween direction="vertical" size="s">
                  {createSecretError && (
                    <Alert type="error" dismissible onDismiss={() => setCreateSecretError(null)}>
                      {createSecretError}
                    </Alert>
                  )}
                  <FormField label="Secret Key" stretch>
                    <Input
                      value={newSecretKey}
                      onChange={({ detail }) => setNewSecretKey(detail.value)}
                      placeholder="e.g., api_key, password, token"
                    />
                  </FormField>
                  <FormField label="Secret Value" stretch>
                    <Input
                      type="password"
                      value={newSecretValue}
                      onChange={({ detail }) => setNewSecretValue(detail.value)}
                      placeholder="Enter the secret value"
                    />
                  </FormField>
                  <Box float="right">
                    <SpaceBetween direction="horizontal" size="xs">
                      <Button
                        variant="link"
                        onClick={() => {
                          setShowCreateSecret(false);
                          setNewSecretKey('');
                          setNewSecretValue('');
                          setCreateSecretError(null);
                        }}
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="primary"
                        onClick={handleCreateSecret}
                        loading={creatingSecret}
                        disabled={!newSecretKey.trim() || !newSecretValue.trim()}
                      >
                        Create
                      </Button>
                    </SpaceBetween>
                  </Box>
                </SpaceBetween>
              </Container>
            )}
          </SpaceBetween>
        )}

        {stepType === 'validation' && (
          <>
            <FormField label="Validation Type" stretch>
              <Select
                selectedOption={VALIDATION_TYPE_OPTIONS.find(opt => opt.value === validationType) || null}
                onChange={({ detail }) => {
                  const newType = detail.selectedOption?.value || 'bool';
                  setValidationType(newType);
                  setValidationValue('');
                  setBooleanInputMode('true');
                  // Reset operator to first available option for the new type
                  if (newType === 'string') {
                    setValidationOperator('exact');
                  } else if (newType === 'number') {
                    setValidationOperator('equals');
                  } else if (newType === 'date') {
                    setValidationOperator('equals');
                  }
                }}
                options={VALIDATION_TYPE_OPTIONS}
              />
            </FormField>

            {validationType === 'bool' && (
              <>
                <FormField
                  stretch
                  label="Expected Boolean Value"
                  description="Select true/false or use a variable"
                >
                  <Select
                    selectedOption={BOOLEAN_OPTIONS.find(opt => opt.value === booleanInputMode) || null}
                    onChange={({ detail }) => {
                      const mode = detail.selectedOption?.value || 'true';
                      setBooleanInputMode(mode);
                      if (mode === 'true' || mode === 'false') {
                        setValidationValue(mode);
                      } else {
                        setValidationValue('');
                      }
                    }}
                    options={BOOLEAN_OPTIONS}
                  />
                </FormField>
                {booleanInputMode === 'variable' && (
                  <FormField
                    stretch
                    label="Variable Expression"
                    description="Enter a variable that evaluates to a boolean (e.g., {{myBooleanVar}})"
                  >
                    <Input
                      value={validationValue}
                      onChange={({ detail }) => setValidationValue(detail.value)}
                      placeholder="{{myBooleanVar}}"
                    />
                  </FormField>
                )}
              </>
            )}

            {(validationType === 'string' || validationType === 'number') && (
              <>
                <FormField label="Comparison Operator" stretch>
                  <Select
                    selectedOption={
                      VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS]
                        ?.find(opt => opt.value === validationOperator) || null
                    }
                    onChange={({ detail }) => setValidationOperator(detail.selectedOption?.value ||
                      (validationType === 'string' ? 'exact' : 'equals'))}
                    options={VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS] || []}
                  />
                </FormField>

                <FormField
                  stretch
                  label="Expected Value"
                  description={
                    validationType === 'number'
                      ? 'Enter a numeric value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                      : 'Enter the expected text value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                  }
                >
                  <Input
                    value={validationValue}
                    onChange={({ detail }) => {
                      console.log(typeof detail.value.toString())
                      setValidationValue(detail.value.toString())
                    }}
                    placeholder={
                      validationType === 'number'
                        ? 'Enter a number (e.g., 42, 3.14) or use variables like {{UniqueID}}'
                        : 'Enter expected value or use variables like {{UniqueID}}, {{Time}}'
                    }
                    type="text"
                  />
                </FormField>
              </>
            )}
            {validationType === 'date' && (
              <DateValidationEditor
                validationOperator={validationOperator}
                setValidationOperator={setValidationOperator}
                validationValue={validationValue}
                setValidationValue={setValidationValue}
              />
            )}
          </>
        )}

        {stepType === 'retrieve_value' && (
          <>
            <FormField
              stretch
              label="Value Source"
              description="Where to read the value from"
            >
              <Select
                selectedOption={{ label: valueSource === 'url' ? 'Page URL' : 'Screen (AI vision)', value: valueSource }}
                onChange={({ detail }) => setValueSource(detail.selectedOption?.value || 'screen')}
                options={[
                  { label: 'Screen (AI vision)', value: 'screen', description: 'Nova Act reads the value from the page visually' },
                  { label: 'Page URL', value: 'url', description: 'Extract from the current page URL using an optional regex pattern' },
                ]}
              />
            </FormField>

            {valueSource === 'url' && (
              <Alert type="info">
                The instruction field becomes a regex pattern. Use a capture group to extract a substring
                (e.g., <code>confirmationId=([A-Z0-9]+)</code>). Leave empty to capture the full URL.
              </Alert>
            )}

            <FormField
              stretch
              label="Variable Name"
              description="Name for the captured variable (will be available as {{variableName}} in subsequent steps)"
            >
              <Input
                value={captureVariable}
                onChange={({ detail }) => setCaptureVariable(detail.value)}
                placeholder="e.g., product_price, user_id, status"
              />
            </FormField>

            <FormField
              stretch
              label="Value Type"
              description="Expected type of the retrieved value"
            >
              <Select
                selectedOption={VALUE_TYPE_OPTIONS.find(opt => opt.value === valueType) || null}
                onChange={({ detail }) => setValueType(detail.selectedOption?.value || 'string')}
                options={VALUE_TYPE_OPTIONS}
              />
            </FormField>

            {valueType === 'date' && (
              <DateFormatSelect
                value={valueFormat}
                onChange={setValueFormat}
                label="Date Format"
              />
            )}
          </>
        )}

        {stepType === 'assertion' && (
          <>
            <FormField
              stretch
              label="Runtime Variable"
              description="Name of the runtime variable to compare (captured from previous retrieve_value steps)"
            >
              <Select
                selectedOption={
                  assertionVariable ?
                    { label: assertionVariable, value: assertionVariable } :
                    null
                }
                onChange={({ detail }) => setAssertionVariable(detail.selectedOption?.value || '')}
                options={getAvailableRuntimeVariables()}
                placeholder="Select a runtime variable"
                empty="No runtime variables available. Add retrieve_value steps first."
                filteringType="auto"
                expandToViewport={true}
              />
            </FormField>

            <FormField label="Validation Type" stretch>
              <Select
                selectedOption={VALIDATION_TYPE_OPTIONS.find(opt => opt.value === validationType) || null}
                onChange={({ detail }) => {
                  const newType = detail.selectedOption?.value || 'bool';
                  setValidationType(newType);
                  setValidationValue('');
                  setBooleanInputMode('true');
                  // Reset operator to first available option for the new type
                  if (newType === 'string') {
                    setValidationOperator('exact');
                  } else if (newType === 'number') {
                    setValidationOperator('equals');
                  } else if (newType === 'date') {
                    setValidationOperator('equals');
                  }
                }}
                options={VALIDATION_TYPE_OPTIONS}
              />
            </FormField>

            {validationType === 'bool' && (
              <>
                <FormField
                  stretch
                  label="Expected Boolean Value"
                  description="Select true/false or use a variable"
                >
                  <Select
                    selectedOption={BOOLEAN_OPTIONS.find(opt => opt.value === booleanInputMode) || null}
                    onChange={({ detail }) => {
                      const mode = detail.selectedOption?.value || 'true';
                      setBooleanInputMode(mode);
                      if (mode === 'true' || mode === 'false') {
                        setValidationValue(mode);
                      } else {
                        setValidationValue('');
                      }
                    }}
                    options={BOOLEAN_OPTIONS}
                  />
                </FormField>
                {booleanInputMode === 'variable' && (
                  <FormField
                    stretch
                    label="Variable Expression"
                    description="Enter a variable that evaluates to a boolean (e.g., {{myBooleanVar}})"
                  >
                    <Input
                      value={validationValue}
                      onChange={({ detail }) => setValidationValue(detail.value)}
                      placeholder="{{myBooleanVar}}"
                    />
                  </FormField>
                )}
              </>
            )}

            {(validationType === 'string' || validationType === 'number') && (
              <>
                <FormField label="Comparison Operator" stretch>
                  <Select
                    selectedOption={
                      VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS]
                        ?.find(opt => opt.value === validationOperator) || null
                    }
                    onChange={({ detail }) => setValidationOperator(detail.selectedOption?.value ||
                      (validationType === 'string' ? 'exact' : 'equals'))}
                    options={VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS] || []}
                  />
                </FormField>

                <FormField
                  stretch
                  label="Expected Value"
                  description={
                    validationType === 'number'
                      ? 'Enter a numeric value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                      : 'Enter the expected text value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                  }
                >
                  <Input
                    value={validationValue}
                    onChange={({ detail }) => {
                      console.log(typeof detail.value.toString())
                      setValidationValue(detail.value.toString())
                    }}
                    placeholder={
                      validationType === 'number'
                        ? 'Enter a number (e.g., 42, 3.14) or use variables like {{UniqueID}}'
                        : 'Enter expected value or use variables like {{UniqueID}}, {{Time}}'
                    }
                    type="text"
                  />
                </FormField>
              </>
            )}
            {validationType === 'date' && (
              <DateValidationEditor
                validationOperator={validationOperator}
                setValidationOperator={setValidationOperator}
                validationValue={validationValue}
                setValidationValue={setValidationValue}
              />
            )}
          </>
        )}

        {stepType === 'network_assertion' && (
          <>
            {/* URL pattern, method, and timeout in a single row.
                URL gets the majority of space; method and timeout are compact. */}
            <Grid gridDefinition={[{ colspan: 7 }, { colspan: 3 }, { colspan: 2 }]}>
              <FormField
                stretch
                label="URL pattern"
                description="Playwright glob, e.g. **/api/users"
              >
                <Input
                  value={networkUrlPattern}
                  onChange={({ detail }) => setNetworkUrlPattern(detail.value)}
                  placeholder="**/api/users"
                />
              </FormField>

              <FormField
                label="HTTP method"
                description="Empty = any"
              >
                <Select
                  selectedOption={
                    NETWORK_METHOD_OPTIONS.find(opt => opt.value === networkMethod)
                    ?? NETWORK_METHOD_OPTIONS[0]
                  }
                  onChange={({ detail }) => setNetworkMethod(detail.selectedOption?.value || '')}
                  options={NETWORK_METHOD_OPTIONS}
                />
              </FormField>

              <FormField
                label="Timeout (s)"
                description={`Max ${NETWORK_TIMEOUT_MAX}s`}
              >
                <Input
                  value={networkTimeout}
                  onChange={({ detail }) => setNetworkTimeout(detail.value)}
                  type="number"
                  inputMode="numeric"
                />
              </FormField>
            </Grid>

            <ExpandableSection
              headerText="Request assertion (optional)"
              headerDescription="Verify the body of the captured request."
            >
              <SpaceBetween direction="vertical" size="m">
                <FormField
                  stretch
                  label="Request body match type"
                  description="How the expected body below is compared to the captured request body."
                >
                  <SegmentedControl
                    selectedId={networkBodyMatchType}
                    onChange={({ detail }) =>
                      setNetworkBodyMatchType(detail.selectedId || 'exact')
                    }
                    options={NETWORK_REQUEST_MATCH_TYPE_SEGMENTS}
                  />
                </FormField>

                <FormField
                  stretch
                  label="Expected request body (JSON)"
                  description={
                    networkBodyMatchType === 'schema'
                      ? `JSON Schema Draft 2020-12 document. External $ref (http/https/file) is rejected. Max ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes.`
                      : `JSON template. Leave empty to skip the body check. Max ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes.`
                  }
                  constraintText={`${new TextEncoder().encode(networkRequestBody).length.toLocaleString()} / ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes`}
                  warningText={
                    new TextEncoder().encode(networkRequestBody).length > NETWORK_BODY_WARN_BYTES
                      ? 'Approaching size limit'
                      : undefined
                  }
                  errorText={
                    new TextEncoder().encode(networkRequestBody).length > NETWORK_BODY_BYTE_LIMIT
                      ? `Body exceeds size limit (${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes)`
                      : undefined
                  }
                >
                  <Textarea
                    value={networkRequestBody}
                    onChange={({ detail }) => setNetworkRequestBody(detail.value)}
                    placeholder={
                      networkBodyMatchType === 'schema'
                        ? '{"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}'
                        : '{"user": {"name": "John"}}'
                    }
                    rows={4}
                  />
                </FormField>
              </SpaceBetween>
            </ExpandableSection>

            <ExpandableSection
              headerText="Response assertion (optional)"
              headerDescription="Verify the response status and/or body shape."
            >
              <SpaceBetween direction="vertical" size="m">
                <FormField
                  stretch
                  label="Expected status code"
                  description={`Optional — integer between ${NETWORK_STATUS_MIN} and ${NETWORK_STATUS_MAX}. Leave empty to skip the status check.`}
                  errorText={
                    networkResponseStatus.trim() &&
                    (() => {
                      const n = parseInt(networkResponseStatus, 10);
                      return Number.isNaN(n) || n < NETWORK_STATUS_MIN || n > NETWORK_STATUS_MAX
                        ? `Status must be between ${NETWORK_STATUS_MIN} and ${NETWORK_STATUS_MAX}`
                        : undefined;
                    })() || undefined
                  }
                >
                  <Input
                    value={networkResponseStatus}
                    onChange={({ detail }) => setNetworkResponseStatus(detail.value)}
                    type="number"
                    inputMode="numeric"
                    placeholder="201"
                  />
                </FormField>

                <FormField
                  stretch
                  label="Response body match type"
                  description='"Exact" is deliberately not offered on the response side — response payloads commonly contain non-deterministic values (timestamps, generated ids). Use a schema with "const" for strict comparisons.'
                >
                  <SegmentedControl
                    selectedId={networkResponseBodyMatchType}
                    onChange={({ detail }) =>
                      setNetworkResponseBodyMatchType(detail.selectedId || 'subset')
                    }
                    options={NETWORK_RESPONSE_MATCH_TYPE_SEGMENTS}
                  />
                </FormField>

                <FormField
                  stretch
                  label="Expected response body (JSON)"
                  description={
                    networkResponseBodyMatchType === 'schema'
                      ? `JSON Schema Draft 2020-12 document. External $ref (http/https/file) is rejected. Max ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes.`
                      : `JSON template. Every key/value in the template must appear in the response; extra keys are ignored. Max ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes.`
                  }
                  constraintText={`${new TextEncoder().encode(networkResponseBody).length.toLocaleString()} / ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes`}
                  warningText={
                    new TextEncoder().encode(networkResponseBody).length > NETWORK_BODY_WARN_BYTES
                      ? 'Approaching size limit'
                      : undefined
                  }
                  errorText={
                    new TextEncoder().encode(networkResponseBody).length > NETWORK_BODY_BYTE_LIMIT
                      ? `Response body exceeds size limit (${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes)`
                      : undefined
                  }
                >
                  <Textarea
                    value={networkResponseBody}
                    onChange={({ detail }) => setNetworkResponseBody(detail.value)}
                    placeholder={
                      networkResponseBodyMatchType === 'schema'
                        ? '{"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}'
                        : '{"id": "abc-123"}'
                    }
                    rows={5}
                  />
                </FormField>
              </SpaceBetween>
            </ExpandableSection>

            <ExpandableSection
              headerText="Response mock (optional)"
              headerDescription="Intercept the request and return a fixed response — useful for error states or edge cases without touching the real backend."
            >
              <SpaceBetween direction="vertical" size="m">
                <FormField
                  stretch
                  label="Mock response (JSON)"
                  description={`Shape: {"status": 201, "body": {...}, "headers": {...}}. Max ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes.`}
                  constraintText={`${new TextEncoder().encode(networkMockResponse).length.toLocaleString()} / ${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes`}
                  warningText={
                    new TextEncoder().encode(networkMockResponse).length > NETWORK_BODY_WARN_BYTES
                      ? 'Approaching size limit'
                      : undefined
                  }
                  errorText={
                    new TextEncoder().encode(networkMockResponse).length > NETWORK_BODY_BYTE_LIMIT
                      ? `Mock response exceeds size limit (${NETWORK_BODY_BYTE_LIMIT.toLocaleString()} bytes)`
                      : undefined
                  }
                >
                  <Textarea
                    value={networkMockResponse}
                    onChange={({ detail }) => setNetworkMockResponse(detail.value)}
                    placeholder='{"status": 201, "body": {"id": "abc-123"}}'
                    rows={4}
                  />
                </FormField>

                {networkMockResponse.trim() && (
                  <FormField
                    label="Passthrough mock"
                    description="Fetch the real response then merge the fields above on top. Leave off for a fully static mock."
                  >
                    <Toggle
                      checked={networkMockPassthrough}
                      onChange={({ detail }) => setNetworkMockPassthrough(detail.checked)}
                    >
                      Passthrough
                    </Toggle>
                  </FormField>
                )}
              </SpaceBetween>
            </ExpandableSection>
          </>
        )}

        {/* Template Info Section */}
        {step?.template_id && (
          <Container
            header={
              <Header variant="h3">
                Template Information
              </Header>
            }
          >
            <SpaceBetween direction="vertical" size="m">
              <div>
                <Box variant="awsui-key-label">Source Template</Box>
                <Link
                  href={`/templates/${step.template_id}`}
                  external
                  externalIconAriaLabel="Opens in new tab"
                >
                  View Template
                </Link>
                {step.template_version && (
                  <Box variant="span" color="text-body-secondary" margin={{ left: 'xs' }}>
                    (v{step.template_version})
                  </Box>
                )}
              </div>

              <div>
                <Box variant="awsui-key-label">Status</Box>
                {loadingTemplateStep ? (
                  <Box color="text-body-secondary">
                    <Spinner /> Checking for updates...
                  </Box>
                ) : templateDifferences.length > 0 ? (
                  <Box color="text-status-warning">
                    ⚠ Out of sync ({templateDifferences.length} {templateDifferences.length === 1 ? 'change' : 'changes'} detected)
                  </Box>
                ) : templateStep ? (
                  <Box color="text-status-success">
                    ✓ Up to date
                  </Box>
                ) : (
                  <Box color="text-body-secondary">
                    Unable to check status
                  </Box>
                )}
              </div>

              {templateDifferences.length > 0 && (
                <ExpandableSection headerText="View changes" variant="footer">
                  <SpaceBetween direction="vertical" size="s">
                    {templateDifferences.map((diff, index) => (
                      <Container key={index}>
                        <SpaceBetween direction="vertical" size="xs">
                          <Box variant="strong" color="text-label">{diff.field}</Box>
                          <div>
                            <Box 
                              padding={{ vertical: 'xs', horizontal: 's' }}
                              margin={{ bottom: 'xs' }}
                            >
                              <SpaceBetween direction="vertical" size="xxs">
                                <Box variant="small" color="text-status-warning">Current:</Box>
                                <Box variant="code">{diff.current}</Box>
                              </SpaceBetween>
                            </Box>
                            <Box 
                              padding={{ vertical: 'xs', horizontal: 's' }}
                            >
                              <SpaceBetween direction="vertical" size="xxs">
                                <Box variant="small" color="text-status-success">Template:</Box>
                                <Box variant="code">{diff.template}</Box>
                              </SpaceBetween>
                            </Box>
                          </div>
                        </SpaceBetween>
                      </Container>
                    ))}
                  </SpaceBetween>
                </ExpandableSection>
              )}

              {onUpdateFromTemplate && templateDifferences.length > 0 && (
                <Button
                  iconName="refresh"
                  onClick={handleUpdateFromTemplate}
                  loading={updatingFromTemplate}
                  disabled={updatingFromTemplate || saving}
                >
                  Update from Template
                </Button>
              )}
            </SpaceBetween>
          </Container>
        )}
      </SpaceBetween>
    </Modal>
  );
}
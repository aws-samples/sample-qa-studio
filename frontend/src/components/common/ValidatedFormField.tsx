import React, { useState, useEffect } from 'react';
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import { FieldValidationConfig, validationManager, ValidationResult } from '../../utils/validation';

interface ValidatedFormFieldProps {
  value: string;
  onChange: (value: string) => void;
  config: FieldValidationConfig;
  disabled?: boolean;
  type?: 'input' | 'textarea';
  rows?: number;
  placeholder?: string;
  showCharacterCount?: boolean;
  showHints?: boolean;
  showExamples?: boolean;
  realTimeValidation?: boolean;
}

export default function ValidatedFormField({
  value,
  onChange,
  config,
  disabled = false,
  type = 'input',
  rows = 4,
  placeholder,
  showCharacterCount = true,
  showHints = true,
  showExamples = false,
  realTimeValidation = true
}: ValidatedFormFieldProps) {
  const [validationResult, setValidationResult] = useState<ValidationResult>({ isValid: true });
  const [isTouched, setIsTouched] = useState(false);
  const [showAllHints, setShowAllHints] = useState(false);
  const [showHintsPanel, setShowHintsPanel] = useState(false);

  // Validate on value change
  useEffect(() => {
    if (realTimeValidation && (isTouched || value)) {
      const result = validationManager.validateField(value, config);
      setValidationResult(result);
    }
  }, [value, config, realTimeValidation, isTouched]);

  const handleChange = (newValue: string) => {
    // Don't sanitize during typing, only pass through the raw value
    // Sanitization will happen during validation
    onChange(newValue);
    
    if (!isTouched) {
      setIsTouched(true);
    }
  };

  const handleBlur = () => {
    setIsTouched(true);
    if (!realTimeValidation) {
      const result = validationManager.validateField(value, config);
      setValidationResult(result);
    }
  };

  const getCharacterCountInfo = () => {
    if (!showCharacterCount || !config.rules.maxLength) return null;

    const current = value.length;
    const max = config.rules.maxLength;
    const remaining = max - current;
    
    let color: "text-status-error" | "text-status-warning" | "text-body-secondary" = "text-body-secondary";
    if (remaining < 0) {
      color = "text-status-error";
    } else if (remaining < max * 0.1) {
      color = "text-status-warning";
    }

    return (
      <Box variant="small" color={color}>
        {current}/{max} characters {remaining >= 0 ? `(${remaining} remaining)` : '(exceeded)'}
      </Box>
    );
  };

  const getProgressInfo = () => {
    if (!config.rules.minLength || value.length >= config.rules.minLength) return null;

    const current = value.length;
    const min = config.rules.minLength;
    const needed = min - current;

    return (
      <Box variant="small" color="text-status-info">
        {needed} more characters needed (minimum {min})
      </Box>
    );
  };

  const getHintsToggle = () => {
    if (!showHints) return null;

    const hints = validationManager.getFieldHints(config, value);
    if (hints.length === 0) return null;

    return (
      <SpaceBetween direction="horizontal" size="xs" alignItems="center">
        <Button
          variant="inline-icon"
          iconName="status-info"
          onClick={() => setShowHintsPanel(!showHintsPanel)}
          ariaLabel={showHintsPanel ? "Hide tips" : "Show tips"}
        />
        <Box variant="small" color="text-body-secondary">
          {hints.length} tip{hints.length !== 1 ? 's' : ''} available
        </Box>
      </SpaceBetween>
    );
  };

  const getHints = () => {
    if (!showHints || !showHintsPanel) return null;

    const hints = validationManager.getFieldHints(config, value);
    const displayHints = showAllHints ? hints : hints.slice(0, 2);

    if (displayHints.length === 0) return null;

    return (
      <Box variant="small">
        <SpaceBetween direction="vertical" size="xxs">
          <Box variant="strong" fontSize="body-s">Tips:</Box>
          {displayHints.map((hint, index) => (
            <Box key={index} color="text-body-secondary">• {hint}</Box>
          ))}
          {hints.length > 2 && !showAllHints && (
            <Box>
              <button
                type="button"
                onClick={() => setShowAllHints(true)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--color-text-interactive-default)',
                  cursor: 'pointer',
                  fontSize: 'inherit',
                  textDecoration: 'underline'
                }}
              >
                Show {hints.length - 2} more tips
              </button>
            </Box>
          )}
        </SpaceBetween>
      </Box>
    );
  };

  const getExamples = () => {
    if (!showExamples || !config.examples || config.examples.length === 0) return null;

    return (
      <Box variant="small">
        <SpaceBetween direction="vertical" size="xxs">
          <Box variant="strong" fontSize="body-s">Examples:</Box>
          {config.examples.slice(0, 2).map((example, index) => (
            <Box key={index} color="text-body-secondary">• {example}</Box>
          ))}
        </SpaceBetween>
      </Box>
    );
  };

  const getValidationFeedback = () => {
    if (!isTouched && !value) return null;

    return (
      <SpaceBetween direction="vertical" size="xs">
        {validationResult.warning && (
          <Box variant="small" color="text-status-warning">
            ⚠️ {validationResult.warning}
          </Box>
        )}
        {validationResult.suggestion && !validationResult.isValid && (
          <Box variant="small" color="text-status-info">
            💡 {validationResult.suggestion}
          </Box>
        )}
      </SpaceBetween>
    );
  };

  const getDescription = () => {
    const components = [];

    if (config.description) {
      components.push(
        <Box key="description" variant="p">
          {config.description}
        </Box>
      );
    }

    const characterCount = getCharacterCountInfo();
    const progressInfo = getProgressInfo();
    
    if (characterCount || progressInfo) {
      components.push(
        <SpaceBetween key="counts" direction="horizontal" size="s">
          {progressInfo}
          {characterCount}
        </SpaceBetween>
      );
    }

    const validationFeedback = getValidationFeedback();
    if (validationFeedback) {
      components.push(validationFeedback);
    }

    const hintsToggle = getHintsToggle();
    if (hintsToggle) {
      components.push(hintsToggle);
    }

    const hints = getHints();
    if (hints) {
      components.push(hints);
    }

    const examples = getExamples();
    if (examples) {
      components.push(examples);
    }

    if (components.length === 0) return undefined;

    return (
      <SpaceBetween direction="vertical" size="xs">
        {components}
      </SpaceBetween>
    );
  };

  const errorText = (isTouched || value) && !validationResult.isValid 
    ? validationResult.error 
    : undefined;

  const isInvalid = !!errorText;

  if (type === 'textarea') {
    return (
      <FormField
        label={config.label}
        description={getDescription()}
        errorText={errorText}
      >
        <Textarea
          value={value}
          onChange={({ detail }) => handleChange(detail.value)}
          onBlur={handleBlur}
          placeholder={placeholder}
          rows={rows}
          disabled={disabled}
          invalid={isInvalid}
        />
      </FormField>
    );
  }

  return (
    <FormField
      label={config.label}
      description={getDescription()}
      errorText={errorText}
    >
      <Input
        value={value}
        onChange={({ detail }) => handleChange(detail.value)}
        onBlur={handleBlur}
        placeholder={placeholder}
        disabled={disabled}
        invalid={isInvalid}
      />
    </FormField>
  );
}
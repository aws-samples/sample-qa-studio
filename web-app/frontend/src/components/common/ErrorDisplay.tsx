import React from 'react';
import Alert from "@cloudscape-design/components/alert";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import { ErrorState, ERROR_CATEGORIES, errorManager } from '../../utils/errorManager';

interface ErrorDisplayProps {
  error: ErrorState;
  onRetry?: () => void;
  onDismiss?: () => void;
  isRetrying?: boolean;
  showDetails?: boolean;
  showSuggestions?: boolean;
}

export default function ErrorDisplay({
  error,
  onRetry,
  onDismiss,
  isRetrying = false,
  showDetails = true,
  showSuggestions = true
}: ErrorDisplayProps) {
  const category = ERROR_CATEGORIES[error.type];
  const canRetry = errorManager.canRetry(error);
  const userMessage = errorManager.getUserFriendlyMessage(error);
  const suggestions = errorManager.getErrorSuggestions(error);

  const getAlertType = (): "error" | "warning" | "info" => {
    switch (category.icon) {
      case 'warning':
        return 'warning';
      case 'info':
        return 'info';
      case 'error':
      default:
        return 'error';
    }
  };

  const renderRetryButton = () => {
    if (!onRetry || !canRetry) return null;

    const retryText = error.retryCount > 0 
      ? `Retry (${error.retryCount}/${error.maxRetries})` 
      : 'Retry';

    return (
      <Button 
        onClick={onRetry}
        loading={isRetrying}
        disabled={isRetrying}
        variant="primary"
      >
        {retryText}
      </Button>
    );
  };

  const renderSuggestions = () => {
    if (!showSuggestions || suggestions.length === 0) return null;

    return (
      <Box variant="small">
        <strong>Suggestions:</strong>
        <ul style={{ margin: '4px 0', paddingLeft: '20px' }}>
          {suggestions.map((suggestion, index) => (
            <li key={index}>{suggestion}</li>
          ))}
        </ul>
      </Box>
    );
  };

  const renderDetails = () => {
    if (!showDetails) return null;

    const hasDetails = error.details || error.code || error.timestamp;
    if (!hasDetails) return null;

    return (
      <ExpandableSection headerText="Technical Details" variant="footer">
        <SpaceBetween direction="vertical" size="xs">
          {error.details && (
            <Box variant="small">
              <strong>Details:</strong> {error.details}
            </Box>
          )}
          {error.code && (
            <Box variant="small">
              <strong>Error Code:</strong> {error.code}
            </Box>
          )}
          <Box variant="small">
            <strong>Error Type:</strong> {error.type}
          </Box>
          <Box variant="small">
            <strong>Time:</strong> {new Date(error.timestamp).toLocaleString()}
          </Box>
          {error.retryCount > 0 && (
            <Box variant="small">
              <strong>Retry Attempts:</strong> {error.retryCount}/{error.maxRetries}
            </Box>
          )}
        </SpaceBetween>
      </ExpandableSection>
    );
  };

  return (
    <Alert
      type={getAlertType()}
      dismissible={!!onDismiss}
      onDismiss={onDismiss}
      action={renderRetryButton()}
      header={category.title}
    >
      <SpaceBetween direction="vertical" size="s">
        <Box>{userMessage}</Box>
        {renderSuggestions()}
        {renderDetails()}
      </SpaceBetween>
    </Alert>
  );
}

// Convenience component for common error scenarios
interface QuickErrorProps {
  type: ErrorState['type'];
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
  isRetrying?: boolean;
  details?: string;
}

export function QuickError({
  type,
  message,
  onRetry,
  onDismiss,
  isRetrying,
  details
}: QuickErrorProps) {
  const error = errorManager.createError(type, message, { details });
  
  return (
    <ErrorDisplay
      error={error}
      onRetry={onRetry}
      onDismiss={onDismiss}
      isRetrying={isRetrying}
    />
  );
}
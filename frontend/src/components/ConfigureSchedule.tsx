import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  SpaceBetween,
  Container,
  Header,
  Button,
  Box,
  Alert,
  FormField,
  Input,
  Toggle,
  Select,
  ColumnLayout,
  StatusIndicator
} from '@cloudscape-design/components';
import { testSuites, TestSuite, ScheduleConfig } from '../utils/api';
import { ErrorState } from '../utils/errorManager';
import { ContainerLoading, HeaderLoading } from './common/LoadingStates';
import Breadcrumb from './common/Breadcrumb';

// Common cron expression presets
const CRON_PRESETS = [
  { label: 'Every day at 9:00 AM', value: '0 9 * * *', description: 'Daily at 9:00 AM' },
  { label: 'Every weekday at 9:00 AM', value: '0 9 * * MON-FRI', description: 'Monday to Friday at 9:00 AM' },
  { label: 'Every Monday at 9:00 AM', value: '0 9 * * MON', description: 'Weekly on Monday at 9:00 AM' },
  { label: 'Every hour', value: '0 * * * *', description: 'At the start of every hour' },
  { label: 'Every 6 hours', value: '0 */6 * * *', description: 'Every 6 hours' },
  { label: 'Every Sunday at midnight', value: '0 0 * * SUN', description: 'Weekly on Sunday at 00:00' },
  { label: 'First day of month at 9:00 AM', value: '0 9 1 * *', description: 'Monthly on the 1st at 9:00 AM' },
  { label: 'Custom', value: 'custom', description: 'Enter a custom cron expression' }
];

// Common timezones
const TIMEZONES = [
  { label: 'UTC', value: 'UTC' },
  { label: 'America/New_York (EST/EDT)', value: 'America/New_York' },
  { label: 'America/Chicago (CST/CDT)', value: 'America/Chicago' },
  { label: 'America/Denver (MST/MDT)', value: 'America/Denver' },
  { label: 'America/Los_Angeles (PST/PDT)', value: 'America/Los_Angeles' },
  { label: 'Europe/London (GMT/BST)', value: 'Europe/London' },
  { label: 'Europe/Paris (CET/CEST)', value: 'Europe/Paris' },
  { label: 'Asia/Tokyo (JST)', value: 'Asia/Tokyo' },
  { label: 'Asia/Shanghai (CST)', value: 'Asia/Shanghai' },
  { label: 'Australia/Sydney (AEDT/AEST)', value: 'Australia/Sydney' }
];

const ConfigureSchedule: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // State for suite data
  const [suite, setSuite] = useState<TestSuite | null>(null);
  const [loadingSuite, setLoadingSuite] = useState(true);

  // Form state
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<any>(CRON_PRESETS[0]);
  const [cronExpression, setCronExpression] = useState('0 9 * * *');
  const [customCronExpression, setCustomCronExpression] = useState('');
  const [timezone, setTimezone] = useState<any>(TIMEZONES[0]);

  // Next run preview
  const [nextRunTime, setNextRunTime] = useState<string | null>(null);
  const [cronValidationError, setCronValidationError] = useState<string | null>(null);

  // Action states
  const [saving, setSaving] = useState(false);

  // Alert states
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  if (!id) {
    return <Box>Suite ID not found</Box>;
  }

  // Fetch suite details
  const fetchSuite = async () => {
    try {
      setLoadingSuite(true);
      const data = await testSuites.get(id);
      setSuite(data);

      // Initialize form with existing schedule if present
      if (data.schedule_enabled) {
        setScheduleEnabled(data.schedule_enabled);
        
        if (data.schedule_expression) {
          setCronExpression(data.schedule_expression);
          
          // Check if it matches a preset
          const matchingPreset = CRON_PRESETS.find(p => p.value === data.schedule_expression);
          if (matchingPreset) {
            setSelectedPreset(matchingPreset);
          } else {
            setSelectedPreset(CRON_PRESETS[CRON_PRESETS.length - 1]); // Custom
            setCustomCronExpression(data.schedule_expression);
          }
        }
        
        if (data.schedule_timezone) {
          const matchingTimezone = TIMEZONES.find(tz => tz.value === data.schedule_timezone);
          if (matchingTimezone) {
            setTimezone(matchingTimezone);
          }
        }
      }
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch test suite');
    } finally {
      setLoadingSuite(false);
    }
  };

  // Validate cron expression format
  const validateCronExpression = (expression: string): boolean => {
    if (!expression || expression.trim() === '') {
      setCronValidationError('Cron expression is required');
      return false;
    }

    // Basic cron validation: 5 fields (minute hour day month weekday)
    const parts = expression.trim().split(/\s+/);
    if (parts.length !== 5) {
      setCronValidationError('Cron expression must have 5 fields: minute hour day month weekday');
      return false;
    }

    // Validate each field has valid characters
    const validPattern = /^[\d\*\-\,\/A-Z]+$/;
    for (const part of parts) {
      if (!validPattern.test(part)) {
        setCronValidationError('Invalid characters in cron expression');
        return false;
      }
    }

    setCronValidationError(null);
    return true;
  };

  // Calculate next run time
  const calculateNextRun = (expression: string, tz: string) => {
    if (!validateCronExpression(expression)) {
      setNextRunTime(null);
      return;
    }

    try {
      // Simple next run calculation (this is a basic approximation)
      // In production, you'd use a library like cron-parser
      const now = new Date();
      const parts = expression.split(/\s+/);
      const [minute, hour] = parts;

      // Parse minute and hour (handle wildcards and ranges)
      let nextMinute = minute === '*' ? 0 : parseInt(minute);
      let nextHour = hour === '*' ? now.getHours() : parseInt(hour);

      const next = new Date(now);
      next.setHours(nextHour, nextMinute, 0, 0);

      // If the time has passed today, move to tomorrow
      if (next <= now) {
        next.setDate(next.getDate() + 1);
      }

      setNextRunTime(next.toLocaleString('en-US', { 
        timeZone: tz,
        dateStyle: 'full',
        timeStyle: 'long'
      }));
    } catch (err) {
      setNextRunTime('Unable to calculate next run time');
    }
  };

  // Handle preset selection
  const handlePresetChange = (option: any) => {
    setSelectedPreset(option);
    
    if (option.value !== 'custom') {
      setCronExpression(option.value);
      calculateNextRun(option.value, timezone.value);
    } else {
      // Custom preset selected
      if (customCronExpression) {
        setCronExpression(customCronExpression);
        calculateNextRun(customCronExpression, timezone.value);
      }
    }
  };

  // Handle custom cron expression change
  const handleCustomCronChange = (value: string) => {
    setCustomCronExpression(value);
    setCronExpression(value);
    calculateNextRun(value, timezone.value);
  };

  // Handle timezone change
  const handleTimezoneChange = (option: any) => {
    setTimezone(option);
    calculateNextRun(cronExpression, option.value);
  };

  // Save schedule configuration
  const handleSave = async () => {
    // Validate cron expression if schedule is enabled
    if (scheduleEnabled && !validateCronExpression(cronExpression)) {
      setError('Please fix the cron expression errors before saving');
      return;
    }

    try {
      setSaving(true);
      
      const config: ScheduleConfig = {
        schedule_enabled: scheduleEnabled,
        schedule_expression: scheduleEnabled ? cronExpression : '',
        schedule_timezone: scheduleEnabled ? timezone.value : 'UTC'
      };

      await testSuites.updateSchedule(id, config);
      setSuccess('Schedule configuration saved successfully');
      
      // Navigate back to suite detail after a short delay
      setTimeout(() => {
        navigate(`/test-suites/${id}`);
      }, 1500);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to save schedule configuration');
    } finally {
      setSaving(false);
    }
  };

  // Initial data fetch
  useEffect(() => {
    fetchSuite();
  }, [id]);

  // Calculate next run when component loads or dependencies change
  useEffect(() => {
    if (scheduleEnabled && cronExpression) {
      calculateNextRun(cronExpression, timezone.value);
    } else {
      setNextRunTime(null);
    }
  }, [scheduleEnabled, cronExpression, timezone]);

  // Auto-dismiss alerts
  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  return (
    <SpaceBetween direction="vertical" size="l">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { text: 'Home', href: '/' },
          { text: 'Test Suites', href: '/test-suites' },
          { text: suite?.name || 'Loading...', href: `/test-suites/${id}` },
          { text: 'Configure Schedule' }
        ]}
      />

      {/* Alerts */}
      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert type="success" dismissible onDismiss={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Header */}
      {loadingSuite ? (
        <HeaderLoading variant="h1" text="Loading schedule configuration..." />
      ) : (
        <Header
          variant="h1"
          description={`Configure automated execution schedule for "${suite?.name}"`}
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                onClick={() => navigate(`/test-suites/${id}`)}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleSave}
                loading={saving}
                disabled={saving || (scheduleEnabled && !!cronValidationError)}
              >
                Save Schedule
              </Button>
            </SpaceBetween>
          }
        >
          Configure Schedule
        </Header>
      )}

      {/* Schedule Configuration Form */}
      {loadingSuite ? (
        <ContainerLoading title="Schedule Configuration" text="Loading..." />
      ) : (
        <Container
          header={
            <Header variant="h2">
              Schedule Settings
            </Header>
          }
        >
          <SpaceBetween direction="vertical" size="l">
            {/* Enable Schedule Toggle */}
            <FormField
              label="Enable Schedule"
              description="When enabled, this test suite will run automatically according to the schedule below"
            >
              <Toggle
                checked={scheduleEnabled}
                onChange={({ detail }) => setScheduleEnabled(detail.checked)}
              >
                {scheduleEnabled ? 'Enabled' : 'Disabled'}
              </Toggle>
            </FormField>

            {scheduleEnabled && (
              <>
                {/* Cron Expression Preset */}
                <FormField
                  label="Schedule Preset"
                  description="Choose a common schedule or select 'Custom' to enter your own cron expression"
                >
                  <Select
                    selectedOption={selectedPreset}
                    onChange={({ detail }) => handlePresetChange(detail.selectedOption)}
                    options={CRON_PRESETS}
                    placeholder="Select a schedule preset"
                  />
                </FormField>

                {/* Custom Cron Expression */}
                {selectedPreset?.value === 'custom' && (
                  <FormField
                    label="Custom Cron Expression"
                    description="Enter a cron expression (format: minute hour day month weekday)"
                    errorText={cronValidationError || undefined}
                  >
                    <Input
                      value={customCronExpression}
                      onChange={({ detail }) => handleCustomCronChange(detail.value)}
                      placeholder="0 9 * * *"
                    />
                  </FormField>
                )}

                {/* Current Cron Expression Display */}
                <FormField
                  label="Current Expression"
                  description="The cron expression that will be used for scheduling"
                >
                  <Box>
                    <code>{cronExpression}</code>
                  </Box>
                </FormField>

                {/* Timezone Selector */}
                <FormField
                  label="Timezone"
                  description="The timezone in which the schedule will run"
                >
                  <Select
                    selectedOption={timezone}
                    onChange={({ detail }) => handleTimezoneChange(detail.selectedOption)}
                    options={TIMEZONES}
                    placeholder="Select a timezone"
                    filteringType="auto"
                  />
                </FormField>

                {/* Next Run Preview */}
                <Container
                  header={
                    <Header variant="h3">
                      Next Run Preview
                    </Header>
                  }
                >
                  <ColumnLayout columns={1}>
                    {nextRunTime ? (
                      <Box>
                        <StatusIndicator type="success">
                          Next scheduled run
                        </StatusIndicator>
                        <Box variant="p" padding={{ top: 'xs' }}>
                          {nextRunTime}
                        </Box>
                      </Box>
                    ) : (
                      <Box>
                        <StatusIndicator type="info">
                          {cronValidationError ? 'Fix errors to see next run time' : 'Calculating...'}
                        </StatusIndicator>
                      </Box>
                    )}
                  </ColumnLayout>
                </Container>

                {/* Cron Expression Help */}
                <Alert type="info" header="Cron Expression Format">
                  <SpaceBetween direction="vertical" size="xs">
                    <Box>
                      Cron expressions consist of 5 fields: <code>minute hour day month weekday</code>
                    </Box>
                    <Box>
                      <strong>Examples:</strong>
                    </Box>
                    <Box>
                      • <code>0 9 * * *</code> - Every day at 9:00 AM
                    </Box>
                    <Box>
                      • <code>0 9 * * MON-FRI</code> - Every weekday at 9:00 AM
                    </Box>
                    <Box>
                      • <code>0 */6 * * *</code> - Every 6 hours
                    </Box>
                    <Box>
                      • <code>0 0 1 * *</code> - First day of every month at midnight
                    </Box>
                  </SpaceBetween>
                </Alert>
              </>
            )}
          </SpaceBetween>
        </Container>
      )}
    </SpaceBetween>
  );
};

export default ConfigureSchedule;

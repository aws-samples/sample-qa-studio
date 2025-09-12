import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import UsecasePreview from '../UsecasePreview';

describe('UsecasePreview', () => {
  const user = userEvent.setup();

  const mockUsecase = {
    exportVersion: '1.0',
    exportedAt: '2025-01-09T10:00:00Z',
    usecase: {
      name: 'Test Login Flow',
      description: 'Generated from user journey: User logs in to the application',
      starting_url: 'https://example.com/login',
      active: true,
      headless: false,
      tags: ['login', 'authentication']
    },
    steps: [
      {
        sort: 1,
        instruction: 'Navigate to login page',
        step_type: 'navigation',
        secret_key: '',
        capture_variable: '',
        validation_type: '',
        validation_operator: '',
        validation_value: '',
        assertion_variable: '',
        value_step: '',
        value_type: ''
      },
      {
        sort: 2,
        instruction: 'Enter email address',
        step_type: 'navigation',
        secret_key: '',
        capture_variable: '',
        validation_type: '',
        validation_operator: '',
        validation_value: '',
        assertion_variable: '',
        value_step: '',
        value_type: ''
      },
      {
        sort: 3,
        instruction: 'Verify login success',
        step_type: 'validation',
        secret_key: '',
        capture_variable: '',
        validation_type: 'element_visible',
        validation_operator: 'equals',
        validation_value: 'true',
        assertion_variable: '',
        value_step: '',
        value_type: ''
      }
    ],
    variables: [
      {
        key: 'username',
        value: 'test@example.com'
      }
    ],
    secrets: [
      {
        key: 'password',
        description: 'User login password',
        value: null,
        placeholder: 'Enter password'
      }
    ],
    hooks: null
  };

  const defaultProps = {
    usecase: mockUsecase,
    onImport: vi.fn(),
    onRegenerate: vi.fn(),
    isImporting: false
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders usecase information correctly', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByText('Preview Generated Use Case')).toBeInTheDocument();
      expect(screen.getByText('Test Login Flow')).toBeInTheDocument();
      expect(screen.getByText(/generated from user journey/i)).toBeInTheDocument();
      expect(screen.getByText('https://example.com/login')).toBeInTheDocument();
    });

    it('displays step count correctly', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByText('3 steps')).toBeInTheDocument();
    });

    it('displays step types breakdown', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByText(/2 navigation/i)).toBeInTheDocument();
      expect(screen.getByText(/1 validation/i)).toBeInTheDocument();
    });

    it('displays variables count when present', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByText('1 variable')).toBeInTheDocument();
    });

    it('displays secrets count when present', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByText('1 secret')).toBeInTheDocument();
    });

    it('handles usecase with no variables or secrets', () => {
      const usecaseWithoutExtras = {
        ...mockUsecase,
        variables: [],
        secrets: []
      };

      render(<UsecasePreview {...defaultProps} usecase={usecaseWithoutExtras} />);

      expect(screen.getByText('0 variables')).toBeInTheDocument();
      expect(screen.getByText('0 secrets')).toBeInTheDocument();
    });

    it('renders action buttons', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByRole('button', { name: /import use case/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /regenerate/i })).toBeInTheDocument();
    });
  });

  describe('Step Details', () => {
    it('shows expandable step details', async () => {
      render(<UsecasePreview {...defaultProps} />);

      // Look for expandable section
      const expandButton = screen.getByRole('button', { name: /view steps/i });
      expect(expandButton).toBeInTheDocument();

      await user.click(expandButton);

      // Check that step details are shown
      expect(screen.getByText('Navigate to login page')).toBeInTheDocument();
      expect(screen.getByText('Enter email address')).toBeInTheDocument();
      expect(screen.getByText('Verify login success')).toBeInTheDocument();
    });

    it('displays step types correctly in expanded view', async () => {
      render(<UsecasePreview {...defaultProps} />);

      const expandButton = screen.getByRole('button', { name: /view steps/i });
      await user.click(expandButton);

      // Check step type badges/indicators
      const navigationSteps = screen.getAllByText('Navigation');
      const validationSteps = screen.getAllByText('Validation');

      expect(navigationSteps).toHaveLength(2);
      expect(validationSteps).toHaveLength(1);
    });

    it('shows validation details for validation steps', async () => {
      render(<UsecasePreview {...defaultProps} />);

      const expandButton = screen.getByRole('button', { name: /view steps/i });
      await user.click(expandButton);

      // Look for validation-specific details
      expect(screen.getByText('element_visible')).toBeInTheDocument();
      expect(screen.getByText('equals')).toBeInTheDocument();
      expect(screen.getByText('true')).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('calls onImport when import button is clicked', async () => {
      render(<UsecasePreview {...defaultProps} />);

      const importButton = screen.getByRole('button', { name: /import use case/i });
      await user.click(importButton);

      expect(defaultProps.onImport).toHaveBeenCalledTimes(1);
    });

    it('calls onRegenerate when regenerate button is clicked', async () => {
      render(<UsecasePreview {...defaultProps} />);

      const regenerateButton = screen.getByRole('button', { name: /regenerate/i });
      await user.click(regenerateButton);

      expect(defaultProps.onRegenerate).toHaveBeenCalledTimes(1);
    });

    it('disables import button when importing', () => {
      render(<UsecasePreview {...defaultProps} isImporting={true} />);

      const importButton = screen.getByRole('button', { name: /importing/i });
      expect(importButton).toBeDisabled();
    });

    it('shows loading state when importing', () => {
      render(<UsecasePreview {...defaultProps} isImporting={true} />);

      expect(screen.getByText(/importing/i)).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('handles usecase with no steps', () => {
      const usecaseWithNoSteps = {
        ...mockUsecase,
        steps: []
      };

      render(<UsecasePreview {...defaultProps} usecase={usecaseWithNoSteps} />);

      expect(screen.getByText('0 steps')).toBeInTheDocument();
    });

    it('handles usecase with only one step type', () => {
      const usecaseWithOnlyNavigation = {
        ...mockUsecase,
        steps: [
          {
            sort: 1,
            instruction: 'Navigate to page',
            step_type: 'navigation',
            secret_key: '',
            capture_variable: '',
            validation_type: '',
            validation_operator: '',
            validation_value: '',
            assertion_variable: '',
            value_step: '',
            value_type: ''
          }
        ]
      };

      render(<UsecasePreview {...defaultProps} usecase={usecaseWithOnlyNavigation} />);

      expect(screen.getByText('1 step')).toBeInTheDocument();
      expect(screen.getByText(/1 navigation/i)).toBeInTheDocument();
    });

    it('handles very long usecase names gracefully', () => {
      const usecaseWithLongName = {
        ...mockUsecase,
        usecase: {
          ...mockUsecase.usecase,
          name: 'This is a very long usecase name that should be handled gracefully by the component without breaking the layout or causing display issues'
        }
      };

      render(<UsecasePreview {...defaultProps} usecase={usecaseWithLongName} />);

      expect(screen.getByText(/this is a very long usecase name/i)).toBeInTheDocument();
    });

    it('handles usecase with special characters in name', () => {
      const usecaseWithSpecialChars = {
        ...mockUsecase,
        usecase: {
          ...mockUsecase.usecase,
          name: 'Test Case with "Quotes" & Special Characters!'
        }
      };

      render(<UsecasePreview {...defaultProps} usecase={usecaseWithSpecialChars} />);

      expect(screen.getByText(/test case with "quotes" & special characters!/i)).toBeInTheDocument();
    });

    it('handles missing optional fields gracefully', () => {
      const minimalUsecase = {
        exportVersion: '1.0',
        exportedAt: '2025-01-09T10:00:00Z',
        usecase: {
          name: 'Minimal Test Case',
          description: 'Basic test case',
          starting_url: 'https://example.com',
          active: true,
          headless: false,
          tags: []
        },
        steps: [
          {
            sort: 1,
            instruction: 'Basic step',
            step_type: 'navigation',
            secret_key: '',
            capture_variable: '',
            validation_type: '',
            validation_operator: '',
            validation_value: '',
            assertion_variable: '',
            value_step: '',
            value_type: ''
          }
        ],
        variables: [],
        secrets: [],
        hooks: null
      };

      render(<UsecasePreview {...defaultProps} usecase={minimalUsecase} />);

      expect(screen.getByText('Minimal Test Case')).toBeInTheDocument();
      expect(screen.getByText('1 step')).toBeInTheDocument();
      expect(screen.getByText('0 variables')).toBeInTheDocument();
      expect(screen.getByText('0 secrets')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA labels for buttons', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByRole('button', { name: /import use case/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /regenerate/i })).toBeInTheDocument();
    });

    it('supports keyboard navigation', async () => {
      render(<UsecasePreview {...defaultProps} />);

      const importButton = screen.getByRole('button', { name: /import use case/i });
      const regenerateButton = screen.getByRole('button', { name: /regenerate/i });

      // Test tab navigation
      importButton.focus();
      expect(document.activeElement).toBe(importButton);

      await user.tab();
      expect(document.activeElement).toBe(regenerateButton);
    });

    it('provides proper heading structure', () => {
      render(<UsecasePreview {...defaultProps} />);

      expect(screen.getByRole('heading', { name: /preview generated use case/i })).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('handles large number of steps efficiently', () => {
      const usecaseWithManySteps = {
        ...mockUsecase,
        steps: Array.from({ length: 100 }, (_, i) => ({
          sort: i + 1,
          instruction: `Step ${i + 1}`,
          step_type: 'navigation',
          secret_key: '',
          capture_variable: '',
          validation_type: '',
          validation_operator: '',
          validation_value: '',
          assertion_variable: '',
          value_step: '',
          value_type: ''
        }))
      };

      const startTime = performance.now();
      render(<UsecasePreview {...defaultProps} usecase={usecaseWithManySteps} />);
      const endTime = performance.now();

      expect(screen.getByText('100 steps')).toBeInTheDocument();
      expect(endTime - startTime).toBeLessThan(100); // Should render quickly
    });
  });
});
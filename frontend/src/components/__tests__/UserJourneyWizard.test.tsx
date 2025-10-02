import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import UserJourneyWizard from '../UserJourneyWizard';
import { wizardApi, exportImportApi } from '../../utils/api';

// Mock the API modules
vi.mock('../../utils/api', () => ({
  wizardApi: {
    generateUsecase: vi.fn(),
  },
  exportImportApi: {
    importUsecase: vi.fn(),
  },
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Test wrapper component
const TestWrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

describe('UserJourneyWizard', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Form Rendering and Validation', () => {
    it('renders all form fields correctly', () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      expect(screen.getByLabelText(/use case title/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/starting url/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/user journey description/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /generate use case/i })).toBeInTheDocument();
    });

    it('shows validation errors for empty required fields', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      const generateButton = screen.getByRole('button', { name: /generate use case/i });
      
      await act(async () => {
        await user.click(generateButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/title is required/i)).toBeInTheDocument();
        expect(screen.getByText(/starting url is required/i)).toBeInTheDocument();
        expect(screen.getByText(/user journey description is required/i)).toBeInTheDocument();
      });
    });

    it('validates title field correctly', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      const titleInput = screen.getByLabelText(/use case title/i);
      
      // Test too short title
      await act(async () => {
        await user.type(titleInput, 'ab');
        await user.tab(); // Trigger blur event
      });

      await waitFor(() => {
        expect(screen.getByText(/at least 3 characters/i)).toBeInTheDocument();
      });

      // Test too long title
      await act(async () => {
        await user.clear(titleInput);
        await user.type(titleInput, 'a'.repeat(201));
        await user.tab();
      });

      await waitFor(() => {
        expect(screen.getByText(/200 characters or less/i)).toBeInTheDocument();
      });

      // Test invalid characters
      await act(async () => {
        await user.clear(titleInput);
        await user.type(titleInput, 'Title with @#$%');
        await user.tab();
      });

      await waitFor(() => {
        expect(screen.getByText(/letters, numbers/i)).toBeInTheDocument();
      });
    });

    it('validates URL field correctly', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      const urlInput = screen.getByLabelText(/starting url/i);
      
      // Test invalid URL format
      await act(async () => {
        await user.type(urlInput, 'invalid-url');
        await user.tab();
      });

      await waitFor(() => {
        expect(screen.getByText(/must start with http/i)).toBeInTheDocument();
      });

      // Test valid URL
      await act(async () => {
        await user.clear(urlInput);
        await user.type(urlInput, 'https://example.com');
        await user.tab();
      });

      await waitFor(() => {
        expect(screen.queryByText(/must start with http/i)).not.toBeInTheDocument();
      });
    });

    it('validates user journey field correctly', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      const journeyInput = screen.getByLabelText(/user journey description/i);
      
      // Test too short journey
      await act(async () => {
        await user.type(journeyInput, 'Short journey');
        await user.tab();
      });

      await waitFor(() => {
        expect(screen.getByText(/at least 50 characters/i)).toBeInTheDocument();
      });

      // Test journey without action words
      await act(async () => {
        await user.clear(journeyInput);
        await user.type(journeyInput, 'This is a very long description that does not contain any action words and should fail validation because it lacks specific user interactions');
        await user.tab();
      });

      await waitFor(() => {
        expect(screen.getByText(/specific actions/i)).toBeInTheDocument();
      });
    });

    it('clears validation errors when field values are corrected', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      const titleInput = screen.getByLabelText(/use case title/i);
      
      // First, create a validation error
      await act(async () => {
        await user.type(titleInput, 'ab');
        await user.tab();
      });

      await waitFor(() => {
        expect(screen.getByText(/at least 3 characters/i)).toBeInTheDocument();
      });

      // Then fix the error
      await act(async () => {
        await user.clear(titleInput);
        await user.type(titleInput, 'Valid Title');
      });

      await waitFor(() => {
        expect(screen.queryByText(/at least 3 characters/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Form Submission and API Integration', () => {
    const validFormData = {
      title: 'Valid Test Case',
      startingUrl: 'https://example.com',
      userJourney: 'User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully'
    };

    const mockGeneratedUsecase = {
      exportVersion: '1.0',
      exportedAt: '2025-01-09T10:00:00Z',
      usecase: {
        name: 'Valid Test Case',
        description: 'Generated test case',
        starting_url: 'https://example.com',
        active: true,
        headless: false,
        region: 'us-east-1',
        tags: []
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
        }
      ],
      variables: [],
      secrets: [],
      hooks: null
    };

    it('submits form successfully and shows preview', async () => {
      const mockResponse = {
        success: true,
        usecaseData: JSON.stringify(mockGeneratedUsecase),
        message: 'Use case generated successfully'
      };

      vi.mocked(wizardApi.generateUsecase).mockResolvedValue(mockResponse);

      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Fill out the form
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), validFormData.title);
        await user.type(screen.getByLabelText(/starting url/i), validFormData.startingUrl);
        await user.type(screen.getByLabelText(/user journey description/i), validFormData.userJourney);
      });

      // Submit the form
      const generateButton = screen.getByRole('button', { name: /generate use case/i });
      await act(async () => {
        await user.click(generateButton);
      });

      // Verify API was called with correct data
      expect(wizardApi.generateUsecase).toHaveBeenCalledWith({
        title: validFormData.title,
        startingUrl: validFormData.startingUrl,
        userJourney: validFormData.userJourney,
        region: validFormData.executionRegion
      });

      // Wait for preview to appear
      await waitFor(() => {
        expect(screen.getByText(/preview generated use case/i)).toBeInTheDocument();
        expect(screen.getByText(/valid test case/i)).toBeInTheDocument();
      });
    });

    it('shows loading state during generation', async () => {
      // Mock a delayed response
      vi.mocked(wizardApi.generateUsecase).mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          success: true,
          usecaseData: JSON.stringify(mockGeneratedUsecase),
          message: 'Success'
        }), 100))
      );

      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Fill out the form
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), validFormData.title);
        await user.type(screen.getByLabelText(/starting url/i), validFormData.startingUrl);
        await user.type(screen.getByLabelText(/user journey description/i), validFormData.userJourney);
      });

      // Submit the form
      const generateButton = screen.getByRole('button', { name: /generate use case/i });
      await act(async () => {
        await user.click(generateButton);
      });

      // Check for loading state
      expect(screen.getByText(/generating/i)).toBeInTheDocument();
      expect(generateButton).toBeDisabled();

      // Wait for completion
      await waitFor(() => {
        expect(screen.queryByText(/generating/i)).not.toBeInTheDocument();
      });
    });

    it('handles API errors gracefully', async () => {
      const mockError = {
        success: false,
        error: 'AI service is temporarily unavailable'
      };

      vi.mocked(wizardApi.generateUsecase).mockResolvedValue(mockError);

      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Fill out and submit form
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), validFormData.title);
        await user.type(screen.getByLabelText(/starting url/i), validFormData.startingUrl);
        await user.type(screen.getByLabelText(/user journey description/i), validFormData.userJourney);
      });

      const generateButton = screen.getByRole('button', { name: /generate use case/i });
      await act(async () => {
        await user.click(generateButton);
      });

      // Check for error display
      await waitFor(() => {
        expect(screen.getByText(/ai service is temporarily unavailable/i)).toBeInTheDocument();
      });
    });

    it('handles network errors', async () => {
      vi.mocked(wizardApi.generateUsecase).mockRejectedValue(new Error('Network error'));

      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Fill out and submit form
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), validFormData.title);
        await user.type(screen.getByLabelText(/starting url/i), validFormData.startingUrl);
        await user.type(screen.getByLabelText(/user journey description/i), validFormData.userJourney);
      });

      const generateButton = screen.getByRole('button', { name: /generate use case/i });
      await act(async () => {
        await user.click(generateButton);
      });

      // Check for error display
      await waitFor(() => {
        expect(screen.getByText(/unexpected error occurred/i)).toBeInTheDocument();
      });
    });
  });

  describe('Preview and Import Functionality', () => {
    const mockGeneratedUsecase = {
      exportVersion: '1.0',
      exportedAt: '2025-01-09T10:00:00Z',
      usecase: {
        name: 'Test Case',
        description: 'Generated test case',
        starting_url: 'https://example.com',
        active: true,
        headless: false,
        region: 'us-east-1',
        tags: []
      },
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
      ],
      variables: [],
      secrets: [],
      hooks: null
    };

    beforeEach(async () => {
      // Set up component in preview mode
      const mockResponse = {
        success: true,
        usecaseData: JSON.stringify(mockGeneratedUsecase),
        message: 'Success'
      };

      vi.mocked(wizardApi.generateUsecase).mockResolvedValue(mockResponse);
    });

    it('displays preview correctly after generation', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Generate use case first
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), 'Test Case');
        await user.type(screen.getByLabelText(/starting url/i), 'https://example.com');
        await user.type(screen.getByLabelText(/user journey description/i), 'User navigates to page and clicks button to complete the action successfully');
        await user.click(screen.getByRole('button', { name: /generate use case/i }));
      });

      // Check preview content
      await waitFor(() => {
        expect(screen.getByText(/preview generated use case/i)).toBeInTheDocument();
        expect(screen.getByText(/test case/i)).toBeInTheDocument();
        expect(screen.getByText(/1 step/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /import use case/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /regenerate/i })).toBeInTheDocument();
      });
    });

    it('imports use case successfully', async () => {
      const mockImportResponse = {
        success: true,
        usecaseId: 'test-usecase-id',
        message: 'Use case imported successfully'
      };

      vi.mocked(exportImportApi.importUsecase).mockResolvedValue(mockImportResponse);

      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Generate use case first
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), 'Test Case');
        await user.type(screen.getByLabelText(/starting url/i), 'https://example.com');
        await user.type(screen.getByLabelText(/user journey description/i), 'User navigates to page and clicks button to complete the action successfully');
        await user.click(screen.getByRole('button', { name: /generate use case/i }));
      });

      // Wait for preview and then import
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /import use case/i })).toBeInTheDocument();
      });

      await act(async () => {
        await user.click(screen.getByRole('button', { name: /import use case/i }));
      });

      // Verify import API was called
      expect(exportImportApi.importUsecase).toHaveBeenCalledWith(mockGeneratedUsecase);

      // Check for success message and navigation
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/usecase/test-usecase-id');
      });
    });

    it('handles import errors', async () => {
      const mockImportError = {
        success: false,
        error: 'Failed to import use case'
      };

      vi.mocked(exportImportApi.importUsecase).mockResolvedValue(mockImportError);

      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Generate use case first
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), 'Test Case');
        await user.type(screen.getByLabelText(/starting url/i), 'https://example.com');
        await user.type(screen.getByLabelText(/user journey description/i), 'User navigates to page and clicks button to complete the action successfully');
        await user.click(screen.getByRole('button', { name: /generate use case/i }));
      });

      // Wait for preview and then import
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /import use case/i })).toBeInTheDocument();
      });

      await act(async () => {
        await user.click(screen.getByRole('button', { name: /import use case/i }));
      });

      // Check for error message
      await waitFor(() => {
        expect(screen.getByText(/failed to import use case/i)).toBeInTheDocument();
      });
    });

    it('allows regeneration of use case', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Generate use case first
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), 'Test Case');
        await user.type(screen.getByLabelText(/starting url/i), 'https://example.com');
        await user.type(screen.getByLabelText(/user journey description/i), 'User navigates to page and clicks button to complete the action successfully');
        await user.click(screen.getByRole('button', { name: /generate use case/i }));
      });

      // Wait for preview
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /regenerate/i })).toBeInTheDocument();
      });

      // Click regenerate
      await act(async () => {
        await user.click(screen.getByRole('button', { name: /regenerate/i }));
      });

      // Should return to form view
      await waitFor(() => {
        expect(screen.getByLabelText(/use case title/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /generate use case/i })).toBeInTheDocument();
      });

      // Form should retain previous values
      expect(screen.getByDisplayValue('Test Case')).toBeInTheDocument();
      expect(screen.getByDisplayValue('https://example.com')).toBeInTheDocument();
    });

    it('shows loading state during import', async () => {
      // Mock delayed import response
      vi.mocked(exportImportApi.importUsecase).mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          success: true,
          usecaseId: 'test-id',
          message: 'Success'
        }), 100))
      );

      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Generate use case first
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), 'Test Case');
        await user.type(screen.getByLabelText(/starting url/i), 'https://example.com');
        await user.type(screen.getByLabelText(/user journey description/i), 'User navigates to page and clicks button to complete the action successfully');
        await user.click(screen.getByRole('button', { name: /generate use case/i }));
      });

      // Wait for preview and then import
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /import use case/i })).toBeInTheDocument();
      });

      await act(async () => {
        await user.click(screen.getByRole('button', { name: /import use case/i }));
      });

      // Check for loading state
      expect(screen.getByText(/importing/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /import use case/i })).toBeDisabled();
    });
  });

  describe('User Interactions and State Management', () => {
    it('handles form reset correctly', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Fill out form
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), 'Test Title');
        await user.type(screen.getByLabelText(/starting url/i), 'https://example.com');
        await user.type(screen.getByLabelText(/user journey description/i), 'User performs actions on the website and completes the workflow successfully');
      });

      // Verify form has values
      expect(screen.getByDisplayValue('Test Title')).toBeInTheDocument();
      expect(screen.getByDisplayValue('https://example.com')).toBeInTheDocument();

      // Find and click reset/clear button if it exists
      const clearButton = screen.queryByRole('button', { name: /clear|reset/i });
      if (clearButton) {
        await act(async () => {
          await user.click(clearButton);
        });

        // Verify form is cleared
        expect(screen.queryByDisplayValue('Test Title')).not.toBeInTheDocument();
        expect(screen.queryByDisplayValue('https://example.com')).not.toBeInTheDocument();
      }
    });

    it('calls onUsecaseCreated callback when provided', async () => {
      const mockCallback = vi.fn();
      const mockImportResponse = {
        success: true,
        usecaseId: 'test-usecase-id',
        message: 'Success'
      };

      vi.mocked(wizardApi.generateUsecase).mockResolvedValue({
        success: true,
        usecaseData: JSON.stringify({
          exportVersion: '1.0',
          usecase: { name: 'Test', description: 'Test', starting_url: 'https://example.com', active: true, headless: false, region: 'us-east-1', tags: [] },
          steps: [],
          variables: [],
          secrets: [],
          hooks: null
        }),
        message: 'Success'
      });

      vi.mocked(exportImportApi.importUsecase).mockResolvedValue(mockImportResponse);

      render(
        <TestWrapper>
          <UserJourneyWizard onUsecaseCreated={mockCallback} />
        </TestWrapper>
      );

      // Complete the full flow
      await act(async () => {
        await user.type(screen.getByLabelText(/use case title/i), 'Test Case');
        await user.type(screen.getByLabelText(/starting url/i), 'https://example.com');
        await user.type(screen.getByLabelText(/user journey description/i), 'User navigates to page and clicks button to complete the action successfully');
        await user.click(screen.getByRole('button', { name: /generate use case/i }));
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /import use case/i })).toBeInTheDocument();
      });

      await act(async () => {
        await user.click(screen.getByRole('button', { name: /import use case/i }));
      });

      // Verify callback was called
      await waitFor(() => {
        expect(mockCallback).toHaveBeenCalledWith('test-usecase-id');
      });
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA labels and roles', () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      // Check for proper labels
      expect(screen.getByLabelText(/use case title/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/starting url/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/user journey description/i)).toBeInTheDocument();

      // Check for proper button roles
      expect(screen.getByRole('button', { name: /generate use case/i })).toBeInTheDocument();
    });

    it('supports keyboard navigation', async () => {
      render(
        <TestWrapper>
          <UserJourneyWizard />
        </TestWrapper>
      );

      const titleInput = screen.getByLabelText(/use case title/i);
      const urlInput = screen.getByLabelText(/starting url/i);
      const journeyInput = screen.getByLabelText(/user journey description/i);
      const generateButton = screen.getByRole('button', { name: /generate use case/i });

      // Test tab navigation
      titleInput.focus();
      expect(document.activeElement).toBe(titleInput);

      await user.tab();
      expect(document.activeElement).toBe(urlInput);

      await user.tab();
      expect(document.activeElement).toBe(journeyInput);

      await user.tab();
      expect(document.activeElement).toBe(generateButton);
    });
  });
});
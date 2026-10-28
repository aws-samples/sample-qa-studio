import { render, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('../../utils/api', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}));

import WizardSetup from '../wizard/WizardSetup';
import CreateFromTemplate from '../CreateFromTemplate';

// /wizard/start and /templates/{id}/apply create a use case, so the API
// requires application_id (with edit on it). The pages must send it.

function applicationSelect(container: HTMLElement) {
  return createWrapper(container).findAllSelects()
    .find((s) => s.findTrigger().getElement().textContent?.includes('Select an application'))!;
}

describe('WizardSetup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue([{ id: 'app-1', name: 'Shop', base_url: 'https://shop.test' }]);
    mockPost.mockResolvedValue({ sessionId: 's-1', usecaseId: 'uc-1' });
  });

  function fill(container: HTMLElement) {
    const inputs = createWrapper(container).findAllInputs();
    act(() => {
      inputs[0].setInputValue('Login flow');
      inputs[1].setInputValue('https://shop.test');
    });
  }

  it('keeps Start disabled until an application is chosen', async () => {
    const { container } = render(<MemoryRouter><WizardSetup /></MemoryRouter>);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('applications'));
    fill(container);
    const start = createWrapper(container).findAllButtons().find((b) => b.getElement().textContent === 'Start Wizard')!;
    expect(start.isDisabled()).toBe(true);
  });

  it('sends application_id to wizard/start', async () => {
    const { container } = render(<MemoryRouter><WizardSetup /></MemoryRouter>);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('applications'));
    fill(container);
    const select = applicationSelect(container);
    await act(async () => select.openDropdown());
    await waitFor(() => expect(select.findDropdown().findOptions()).toHaveLength(1));
    await act(async () => select.selectOptionByValue('app-1'));
    const start = createWrapper(container).findAllButtons().find((b) => b.getElement().textContent === 'Start Wizard')!;
    expect(start.isDisabled()).toBe(false);
    await act(async () => start.click());
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [endpoint, body] = mockPost.mock.calls[0];
    expect(endpoint).toBe('wizard/start');
    expect(body.application_id).toBe('app-1');
  });
});

describe('CreateFromTemplate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockImplementation(async (endpoint: string) => {
      if (endpoint === 'applications') return [{ id: 'app-1', name: 'Shop', base_url: 'https://shop.test' }];
      if (endpoint === 'templates') return { templates: [{ id: 'tpl-1', name: 'Login', description: '' }] };
      if (endpoint.endsWith('/steps')) return { steps: [] };
      if (endpoint.endsWith('/variables')) return { variables: [] };
      return { id: 'tpl-1', name: 'Login' };
    });
    mockPost.mockResolvedValue({ usecaseId: 'uc-1' });
  });

  it('sends application_id to templates/{id}/apply', async () => {
    const { container } = render(<MemoryRouter><CreateFromTemplate /></MemoryRouter>);
    const wrapper = createWrapper(container);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('templates'));
    const templateSelect = wrapper.findAllSelects()[0];
    await act(async () => templateSelect.openDropdown());
    await waitFor(() => expect(templateSelect.findDropdown().findOptions()).toHaveLength(1));
    await act(async () => templateSelect.selectOptionByValue('tpl-1'));

    const appSelect = applicationSelect(container);
    await act(async () => appSelect.openDropdown());
    await waitFor(() => expect(appSelect.findDropdown().findOptions()).toHaveLength(1));
    await act(async () => appSelect.selectOptionByValue('app-1'));

    const inputs = wrapper.findAllInputs();
    act(() => {
      inputs[0].setInputValue('From template');
      inputs[inputs.length - 1].setInputValue('https://shop.test');
    });
    const create = wrapper.findAllButtons().find((b) => !b.isDisabled() && /Create/.test(b.getElement().textContent || ''))!;
    await act(async () => create.click());
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [endpoint, body] = mockPost.mock.calls[0];
    expect(endpoint).toBe('templates/tpl-1/apply');
    expect(body.application_id).toBe('app-1');
  });
});

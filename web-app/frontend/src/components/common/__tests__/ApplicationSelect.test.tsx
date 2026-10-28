import { render, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const mockGet = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}));

import ApplicationSelect from '../ApplicationSelect';

describe('ApplicationSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue([
      { id: 'app-1', name: 'Shop', base_url: 'https://shop.test' },
      { id: 'app-2', name: 'Admin', base_url: 'https://admin.test' },
    ]);
  });

  it('lists the caller\'s applications and reports the chosen id', async () => {
    const onChange = vi.fn();
    const { container } = render(<ApplicationSelect value="" onChange={onChange} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('applications'));
    const select = createWrapper(container).findSelect()!;
    await act(async () => select.openDropdown());
    await waitFor(() => expect(select.findDropdown().findOptions()).toHaveLength(2));
    await act(async () => select.selectOptionByValue('app-2'));
    expect(onChange).toHaveBeenCalledWith('app-2');
  });

  it('shows the selected application and marks the field required', async () => {
    const { container } = render(<ApplicationSelect value="app-1" onChange={() => {}} errorText="Application is required" />);
    const wrapper = createWrapper(container);
    await waitFor(() => expect(wrapper.findSelect()!.findTrigger().getElement().textContent).toContain('Shop'));
    expect(wrapper.findFormField()!.findConstraint()!.getElement().textContent).toBe('Required');
    expect(wrapper.findFormField()!.findError()!.getElement().textContent).toBe('Application is required');
  });
});

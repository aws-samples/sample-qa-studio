/**
 * SplitPanelProvider / useSplitPanel: a routed page hands a Cloudscape SplitPanel
 * to the root AppLayout through context; the position preference round-trips
 * through localStorage.
 */
import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';
import AppLayout from '@cloudscape-design/components/app-layout';
import SplitPanel from '@cloudscape-design/components/split-panel';

// --- Mocks needed by the App-level wiring test (same set as App.navigation.test.tsx) ---
vi.mock('aws-amplify', () => ({ Amplify: { configure: vi.fn() } }));
vi.mock('@aws-amplify/ui-react', () => ({
  Authenticator: ({ children }: { children: (p: { signOut: () => void; user: unknown }) => React.ReactNode }) =>
    <>{children({ signOut: vi.fn(), user: { username: 'tester' } })}</>,
}));
vi.mock('@aws-amplify/ui-react/styles.css', () => ({}));
vi.mock('../../../amplifyconfiguration.json', () => ({ default: {} }));
vi.mock('../../../auth', async () => {
  const access = await vi.importActual<typeof import('../../../auth/applicationAccess')>('../../../auth/applicationAccess');
  return {
    ...access,
    PermissionsProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    usePermissions: () => ({ isAdmin: false, isTeamLead: false, teams: [], hasScope: () => false, scopes: [], isLoading: false }),
  };
});
vi.mock('../../../utils/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(null),
  },
}));
// The /about route stands in for "a routed page that registers a panel". It is
// deliberately NOT memoised: a new panel element on every render must not loop.
vi.mock('../../About', () => ({
  default: () => {
    const [open, setOpen] = useState(true);
    useSplitPanel({
      panel: <SplitPanel header="Panel from a route">route body</SplitPanel>,
      open,
      onToggle: setOpen,
    });
    return <div data-testid="about-page">about</div>;
  },
}));

import {
  SplitPanelProvider,
  useSplitPanel,
  useSplitPanelLayoutProps,
  SPLIT_PANEL_POSITION_KEY,
  SPLIT_PANEL_I18N,
} from '../splitPanel';
import App from '../../../App';

/** Stand-in for the root AppLayout in App.tsx. */
function Layout({ children }: { children: React.ReactNode }) {
  const layoutProps = useSplitPanelLayoutProps();
  return (
    <>
      <span data-testid="split-panel-position">{layoutProps.splitPanelPreferences.position}</span>
      <AppLayout navigationHide toolsHide content={children} {...layoutProps} />
    </>
  );
}

function Page({ open, onToggle, header = 'Execution 0199' }: { open: boolean; onToggle: (open: boolean) => void; header?: string }) {
  useSplitPanel({
    panel: <SplitPanel header={header} i18nStrings={SPLIT_PANEL_I18N}>panel body</SplitPanel>,
    open,
    onToggle,
  });
  return <div data-testid="page">page</div>;
}

function Harness({ initialOpen = true, mounted = true }: { initialOpen?: boolean; mounted?: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  const [showPage, setShowPage] = useState(mounted);
  const onToggle = (next: boolean) => { onToggleSpy(next); setOpen(next); };
  return (
    <SplitPanelProvider>
      <Layout>
        <button type="button" onClick={() => setShowPage(false)}>unmount page</button>
        {showPage ? <Page open={open} onToggle={onToggle} /> : <div data-testid="other-page">other</div>}
      </Layout>
    </SplitPanelProvider>
  );
}

const onToggleSpy = vi.fn();
const splitPanel = () => createWrapper(document.body).findAppLayout()!.findSplitPanel();

/** Open the gear dialog of the split panel, pick a position tile and confirm. */
async function choosePositionInPreferences(position: 'bottom' | 'side') {
  act(() => { splitPanel()!.findPreferencesButton()!.click(); });
  const modal = await vi.waitFor(() => {
    const m = createWrapper(document.body).findModal();
    expect(m).not.toBeNull();
    return m!;
  });
  act(() => { modal.findContent().findTiles()!.findInputByValue(position)!.click(); });
  const confirm = modal.findFooter()!.findAllButtons()
    .find((b) => b.getElement().textContent?.trim() === SPLIT_PANEL_I18N.preferencesConfirm);
  expect(confirm, 'confirm button in the preferences dialog').toBeDefined();
  act(() => { confirm!.click(); });
}

beforeEach(() => {
  onToggleSpy.mockReset();
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.pushState({}, '', '/');
});

describe('SplitPanelProvider + useSplitPanel', () => {
  it('exposes the localStorage key and the i18n strings', () => {
    expect(SPLIT_PANEL_POSITION_KEY).toBe('qa-studio.splitPanel.position');
    expect(SPLIT_PANEL_I18N.preferencesPositionSide).toBe('Side');
    expect(SPLIT_PANEL_I18N.preferencesPositionBottom).toBe('Bottom');
    expect(SPLIT_PANEL_I18N.openButtonAriaLabel).toBeTruthy();
    expect(SPLIT_PANEL_I18N.closeButtonAriaLabel).toBeTruthy();
    expect(SPLIT_PANEL_I18N.resizeHandleAriaLabel).toBeTruthy();
  });

  it('renders no split panel while nothing is registered', () => {
    render(<Harness mounted={false} />);
    expect(splitPanel()).toBeNull();
  });

  it('shows the registered panel in the layout and removes it when the page unmounts', async () => {
    render(<Harness />);
    expect(splitPanel()).not.toBeNull();
    expect(splitPanel()!.findHeader().getElement()).toHaveTextContent('Execution 0199');
    expect(screen.getByText('panel body')).toBeInTheDocument();

    act(() => { screen.getByRole('button', { name: 'unmount page' }).click(); });
    await screen.findByTestId('other-page');
    expect(splitPanel()).toBeNull();
  });

  it('calls onToggle with the new open state from the close and open buttons', async () => {
    render(<Harness initialOpen />);
    act(() => { splitPanel()!.findCloseButton()!.click(); });
    expect(onToggleSpy).toHaveBeenLastCalledWith(false);

    const openButton = await vi.waitFor(() => {
      const button = splitPanel()!.findOpenButton();
      expect(button).not.toBeNull();
      return button!;
    });
    act(() => { openButton.click(); });
    expect(onToggleSpy).toHaveBeenLastCalledWith(true);
    expect(onToggleSpy).toHaveBeenCalledTimes(2);
  });

  it('defaults the position to bottom when nothing is stored', () => {
    render(<Harness />);
    expect(screen.getByTestId('split-panel-position')).toHaveTextContent('bottom');
  });

  it('reads a stored side position on mount', () => {
    window.localStorage.setItem(SPLIT_PANEL_POSITION_KEY, 'side');
    render(<Harness />);
    expect(screen.getByTestId('split-panel-position')).toHaveTextContent('side');
  });

  it('falls back to bottom on an invalid stored value', () => {
    window.localStorage.setItem(SPLIT_PANEL_POSITION_KEY, 'ceiling');
    render(<Harness />);
    expect(screen.getByTestId('split-panel-position')).toHaveTextContent('bottom');
  });

  it('falls back to bottom when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    render(<Harness />);
    expect(screen.getByTestId('split-panel-position')).toHaveTextContent('bottom');
  });

  it('writes the position chosen in the preferences dialog back to localStorage', async () => {
    render(<Harness />);
    await choosePositionInPreferences('side');
    await vi.waitFor(() => expect(screen.getByTestId('split-panel-position')).toHaveTextContent('side'));
    expect(window.localStorage.getItem(SPLIT_PANEL_POSITION_KEY)).toBe('side');
    expect(splitPanel()!.findOpenPanelSide()).not.toBeNull();
  });

  it('keeps the chosen position even when localStorage refuses the write', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    render(<Harness />);
    await choosePositionInPreferences('side');
    await vi.waitFor(() => expect(screen.getByTestId('split-panel-position')).toHaveTextContent('side'));
  });

  it('throws a clear error when used outside the provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Page open onToggle={() => {}} />)).toThrow(/useSplitPanel must be used within a SplitPanelProvider/);
    expect(() => render(<Layout>x</Layout>)).toThrow(/useSplitPanelLayoutProps must be used within a SplitPanelProvider/);
    spy.mockRestore();
  });
});

describe('App.tsx wiring', () => {
  it('renders a panel registered by a routed page on the root AppLayout', async () => {
    window.history.pushState({}, '', '/about');
    render(<App />);
    await screen.findByTestId('about-page');
    await vi.waitFor(() => {
      const panel = splitPanel();
      expect(panel).not.toBeNull();
      expect(panel!.findHeader().getElement()).toHaveTextContent('Panel from a route');
    });
    expect(screen.getByText('route body')).toBeInTheDocument();
    // Toggling from the layout reaches the page's own state.
    act(() => { splitPanel()!.findCloseButton()!.click(); });
    await vi.waitFor(() => expect(splitPanel()!.findOpenButton()).not.toBeNull());
  });
});

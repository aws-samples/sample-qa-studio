/**
 * Split panel on the root AppLayout.
 *
 * `App.tsx` owns the only Cloudscape `AppLayout` (classic visual mode does not merge
 * nested layouts). A routed page hands its `<SplitPanel>` to that layout with
 * `useSplitPanel({ panel, open, onToggle })`; the layout reads the resulting props
 * with `useSplitPanelLayoutProps()`. The bottom/side position preference is provider
 * state, persisted in localStorage under `SPLIT_PANEL_POSITION_KEY`.
 *
 * Two contexts on purpose: pages subscribe only to the stable registry (register /
 * unregister never change identity), so a registration does not re-render the page
 * that produced it. Only the layout subscribes to the registration itself.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { AppLayoutProps } from '@cloudscape-design/components/app-layout';
import type { SplitPanelProps } from '@cloudscape-design/components/split-panel';

export const SPLIT_PANEL_POSITION_KEY = 'qa-studio.splitPanel.position';

const DEFAULT_POSITION: AppLayoutProps.SplitPanelPosition = 'bottom';

export const SPLIT_PANEL_I18N: SplitPanelProps.I18nStrings = {
  preferencesTitle: 'Split panel preferences',
  preferencesPositionLabel: 'Split panel position',
  preferencesPositionDescription: 'Choose the default split panel position for the service.',
  preferencesPositionSide: 'Side',
  preferencesPositionBottom: 'Bottom',
  preferencesConfirm: 'Confirm',
  preferencesCancel: 'Cancel',
  closeButtonAriaLabel: 'Close panel',
  openButtonAriaLabel: 'Open panel',
  resizeHandleAriaLabel: 'Resize split panel',
};

export interface SplitPanelRegistration {
  /** The `<SplitPanel>` element to show, or `null` to show nothing. */
  panel: React.ReactNode;
  open: boolean;
  /** Called with the new open state when the user opens or closes the panel from the layout. */
  onToggle: (open: boolean) => void;
}

interface SplitPanelRegistry {
  register: (registration: SplitPanelRegistration) => void;
  unregister: () => void;
}

interface SplitPanelLayoutState {
  registration: SplitPanelRegistration | null;
  preferences: AppLayoutProps.SplitPanelPreferences;
  setPreferences: (preferences: AppLayoutProps.SplitPanelPreferences) => void;
}

const SplitPanelRegistryContext = createContext<SplitPanelRegistry | null>(null);
const SplitPanelLayoutContext = createContext<SplitPanelLayoutState | null>(null);

function isPosition(value: unknown): value is AppLayoutProps.SplitPanelPosition {
  return value === 'bottom' || value === 'side';
}

function readStoredPosition(): AppLayoutProps.SplitPanelPosition {
  try {
    const stored = window.localStorage.getItem(SPLIT_PANEL_POSITION_KEY);
    return isPosition(stored) ? stored : DEFAULT_POSITION;
  } catch (error) {
    console.warn('Split panel position could not be read from localStorage; using bottom.', error);
    return DEFAULT_POSITION;
  }
}

function writeStoredPosition(position: AppLayoutProps.SplitPanelPosition): void {
  try {
    window.localStorage.setItem(SPLIT_PANEL_POSITION_KEY, position);
  } catch (error) {
    console.warn('Split panel position could not be saved to localStorage.', error);
  }
}

export function SplitPanelProvider({ children }: { children: React.ReactNode }) {
  const [registration, setRegistration] = useState<SplitPanelRegistration | null>(null);
  const [preferences, setPreferencesState] = useState<AppLayoutProps.SplitPanelPreferences>(() => ({
    position: readStoredPosition(),
  }));

  const register = useCallback((next: SplitPanelRegistration) => setRegistration(next), []);
  const unregister = useCallback(() => setRegistration(null), []);
  const registry = useMemo<SplitPanelRegistry>(() => ({ register, unregister }), [register, unregister]);

  const setPreferences = useCallback((next: AppLayoutProps.SplitPanelPreferences) => {
    const position = isPosition(next.position) ? next.position : DEFAULT_POSITION;
    setPreferencesState({ position });
    writeStoredPosition(position);
  }, []);

  const layoutState = useMemo<SplitPanelLayoutState>(
    () => ({ registration, preferences, setPreferences }),
    [registration, preferences, setPreferences]
  );

  return (
    <SplitPanelRegistryContext.Provider value={registry}>
      <SplitPanelLayoutContext.Provider value={layoutState}>{children}</SplitPanelLayoutContext.Provider>
    </SplitPanelRegistryContext.Provider>
  );
}

/**
 * Register a split panel with the root layout for as long as the calling component is
 * mounted. Re-registers whenever `panel`, `open` or `onToggle` change.
 */
export function useSplitPanel({ panel, open, onToggle }: SplitPanelRegistration): void {
  const registry = useContext(SplitPanelRegistryContext);
  if (!registry) {
    throw new Error('useSplitPanel must be used within a SplitPanelProvider');
  }
  const { register, unregister } = registry;

  useEffect(() => {
    register({ panel, open, onToggle });
    return unregister;
  }, [register, unregister, panel, open, onToggle]);
}

export interface SplitPanelLayoutProps {
  splitPanel: React.ReactNode | undefined;
  splitPanelOpen: boolean;
  onSplitPanelToggle: NonNullable<AppLayoutProps['onSplitPanelToggle']>;
  splitPanelPreferences: AppLayoutProps.SplitPanelPreferences;
  onSplitPanelPreferencesChange: NonNullable<AppLayoutProps['onSplitPanelPreferencesChange']>;
}

/** Props for the root `<AppLayout>`; spread them onto it. */
export function useSplitPanelLayoutProps(): SplitPanelLayoutProps {
  const state = useContext(SplitPanelLayoutContext);
  if (!state) {
    throw new Error('useSplitPanelLayoutProps must be used within a SplitPanelProvider');
  }
  const { registration, preferences, setPreferences } = state;

  const onSplitPanelToggle = useCallback<SplitPanelLayoutProps['onSplitPanelToggle']>(
    ({ detail }) => registration?.onToggle(detail.open),
    [registration]
  );
  const onSplitPanelPreferencesChange = useCallback<SplitPanelLayoutProps['onSplitPanelPreferencesChange']>(
    ({ detail }) => setPreferences(detail),
    [setPreferences]
  );

  return {
    splitPanel: registration?.panel ?? undefined,
    splitPanelOpen: registration?.open ?? false,
    onSplitPanelToggle,
    splitPanelPreferences: preferences,
    onSplitPanelPreferencesChange,
  };
}

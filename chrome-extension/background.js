// Nova Act Recorder - Background Service Worker
// Central coordinator: manages recording state, stores actions, generates prompts

'use strict';

import { SessionManager } from './session-manager.js';
import { ActionStore } from './action-store.js';
import { StorageManager } from './storage-manager.js';
import { ScriptExporter } from './script-exporter.js';
import { serializeRecording } from './recording-serializer.js';

// ─── Core Instances ───

const sessionManager = new SessionManager();
const actionStore = new ActionStore();
const scriptExporter = new ScriptExporter();
const storageManager = new StorageManager();

// ─── Screenshot Storage ───
// Uses chrome.storage.session so screenshots survive service worker restarts
// (which Chrome triggers on tab switches). Keys are prefixed with "ss:" to
// distinguish them from other session storage. JPEG format keeps sizes small.

/** Saves a screenshot to session storage. Fails silently on quota errors. */
async function saveScreenshot(actionId, dataUrl) {
  try {
    await chrome.storage.session.set({ [`ss:${actionId}`]: dataUrl });
  } catch {
    // Quota exceeded or other error — skip silently
  }
}

/** Returns all screenshots as { actionId: dataUrl }. */
async function getAllScreenshots() {
  try {
    const all = await chrome.storage.session.get(null);
    const screenshots = {};
    for (const key of Object.keys(all)) {
      if (key.startsWith('ss:')) {
        screenshots[key.slice(3)] = all[key];
      }
    }
    return screenshots;
  } catch {
    return {};
  }
}

/** Removes all screenshots from session storage. */
async function clearAllScreenshots() {
  try {
    const all = await chrome.storage.session.get(null);
    const keys = Object.keys(all).filter(k => k.startsWith('ss:'));
    if (keys.length > 0) await chrome.storage.session.remove(keys);
  } catch { /* ignore */ }
}

/** Removes a single screenshot from session storage. */
async function deleteScreenshot(actionId) {
  try {
    await chrome.storage.session.remove(`ss:${actionId}`);
  } catch { /* ignore */ }
}

// ─── Side Panel: open on extension icon click ───

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});

// ─── Task 2.5: Navigation Capture ───

const USER_INITIATED_TRANSITIONS = ['link', 'typed', 'auto_bookmark', 'generated', 'form_submit'];

/**
 * Listens for navigation events and captures user-initiated navigations
 * as navigation actions during an active recording session.
 */
chrome.webNavigation.onCommitted.addListener((details) => {
  // Only capture main frame navigations
  if (details.frameId !== 0) return;

  // Only capture if we're recording and it's the right tab (tab-scoping)
  if (!sessionManager.shouldCaptureAction(details.tabId)) return;

  // Only capture user-initiated transitions
  if (!USER_INITIATED_TRANSITIONS.includes(details.transitionType)) return;

  /** @type {import('./types.js').RawAction} */
  const action = {
    type: 'navigation',
    timestamp: Date.now(),
    url: details.url,
    value: details.url,
  };

  const entry = handleCapturedAction(action);

  // Relay to starting tab so page-level CDP consumers see cross-tab navigations
  relayEntryToStartingTab(entry, [details.tabId]);
});

// ─── Task 3.3: Tab-Scoping Logic ───

/**
 * Moves recording to the newly activated tab.
 * Records a tab_switch action and ensures the new tab's content script is recording.
 * Does NOT send STOP_RECORDING to the old tab — background's shouldCaptureAction()
 * filters by tab ID, so the old tab's events are simply ignored. This avoids
 * disrupting the old tab's state (activeInputElement, scroll tracking, etc.)
 * so everything works correctly when the user switches back.
 */
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  if (!sessionManager.isRecording()) return;

  const previousTabId = sessionManager.getActiveTabId();
  if (activeInfo.tabId === previousTabId) return;

  // Record a tab_switch action for the destination tab
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    /** @type {import('./types.js').RawAction} */
    const action = {
      type: 'tab_switch',
      timestamp: Date.now(),
      url: tab.url || '',
      value: tab.url || '',
      tabTitle: tab.title || '',
      tabId: activeInfo.tabId,
    };
    const entry = handleCapturedAction(action);

    // Forward the full entry (with id/prompt) to the previous tab, the new
    // tab, and the starting tab so CDP page-level collectors can pick it up.
    // handleCapturedAction already broadcasts to sessionManager.getActiveTabId()
    // which is still previousTabId at this point (handleTabActivated hasn't
    // been called yet). So we must NOT re-send to previousTabId — that would
    // cause a duplicate.
    const broadcastTargets = [activeInfo.tabId];
    if (previousTabId) {
      broadcastTargets.push(previousTabId);
    }

    // Send to the NEW tab (handleCapturedAction sent to the old one)
    chrome.tabs.sendMessage(activeInfo.tabId, { kind: 'BROADCAST_ENTRY', entry }).catch(() => { });

    // Also relay to starting tab if it wasn't already a broadcast target
    relayEntryToStartingTab(entry, broadcastTargets);
  } catch {
    // Tab may not be accessible (e.g. chrome:// pages) — skip silently
  }

  // Move the recording session to the new tab
  sessionManager.handleTabActivated(activeInfo.tabId);

  // Ensure new tab's content script knows to record
  chrome.tabs.sendMessage(activeInfo.tabId, { kind: 'START_RECORDING' }).catch(() => { });

  persistActiveSession(sessionManager.getSession());
});

// Tab close no longer auto-stops recording. Multi-tab workflows mean tabs
// get opened and closed freely during a session. Recording is only stopped
// explicitly via the Stop button or side panel close.

// ─── Action Handling ───

/**
 * Captures a screenshot of the currently visible tab and persists it to
 * chrome.storage.session so it survives service worker restarts.
 * Uses JPEG to keep within the 10MB session storage quota.
 * Fails silently — screenshots are best-effort and should never block recording.
 * @param {string} actionId - The action ID to associate the screenshot with
 */
async function captureScreenshotForAction(actionId) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return;
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 85 });
    await saveScreenshot(actionId, dataUrl);
    // Relay to content script for page-level consumers (CDP bridge, etc.)
    chrome.tabs.sendMessage(tab.id, {
      kind: 'BROADCAST_SCREENSHOT',
      actionId,
      dataUrl,
    }).catch(() => { });

    // Also relay screenshot to starting tab if different from active tab
    const session = sessionManager.getSession();
    const startingTabId = session ? session.startingTabId : null;
    if (startingTabId && startingTabId !== tab.id) {
      chrome.tabs.sendMessage(startingTabId, {
        kind: 'BROADCAST_SCREENSHOT',
        actionId,
        dataUrl,
      }).catch(() => { });
    }
  } catch {
    // Silently fail — restricted pages (chrome://, etc.) can't be captured
  }
}

/**
 * Handles a captured action from content script or navigation listener.
 * Adds it to the ActionStore and syncs with SessionManager.
 * Returns the processed ActionEntry (with id/prompt) so callers can
 * broadcast the full entry to page-level consumers (CDP collectors).
 * @param {import('./types.js').RawAction} action
 * @returns {import('./types.js').ActionEntry}
 */
function handleCapturedAction(action) {
  const entry = actionStore.addAction(action);
  // Sync the action store's actions with the session manager
  sessionManager.setActions(actionStore.getActionsRef());

  // Task 3.5: Persist active session on each action
  persistActiveSession(sessionManager.getSession());

  // Capture screenshot in the background (non-blocking)
  captureScreenshotForAction(entry.id);

  // Broadcast full entry (with id/prompt) to the active tab's page context
  // so CDP collectors get complete ActionEntry objects for use case generation.
  const activeTabId = sessionManager.getActiveTabId();
  if (activeTabId) {
    chrome.tabs.sendMessage(activeTabId, { kind: 'BROADCAST_ENTRY', entry }).catch(() => { });
  }

  return entry;
}

/**
 * Relays a full ActionEntry to the starting tab's page context so that
 * page-level consumers (e.g. CDP collectors via window.__novaActions) see
 * actions from ALL tabs, not just the tab they're attached to.
 *
 * Only sends when the source tab differs from the starting tab to avoid
 * duplicates (handleCapturedAction already broadcasts to the active tab).
 *
 * @param {import('./types.js').ActionEntry} entry - The processed entry to relay
 * @param {number[]} alreadyBroadcastTo - Tab IDs that already received this entry
 */
function relayEntryToStartingTab(entry, alreadyBroadcastTo = []) {
  const session = sessionManager.getSession();
  if (!session) return;
  const startingTabId = session.startingTabId;
  if (!startingTabId) return;
  if (alreadyBroadcastTo.includes(startingTabId)) return;
  chrome.tabs.sendMessage(startingTabId, {
    kind: 'BROADCAST_ENTRY',
    entry,
  }).catch(() => { });
}

// ─── Task 3.5: Service Worker State Recovery ───

/**
 * Persists the active session to chrome.storage.local.
 * Also persists the current actions separately so they survive service worker restarts.
 * @param {import('./types.js').RecordingSession|null} session
 */
function persistActiveSession(session) {
  try {
    chrome.storage.local.set({
      activeSession: session,
      currentActions: actionStore.getActions(),
    });
  } catch {
    // Silently fail — storage errors shouldn't break recording
  }
}

/**
 * Restores session state from chrome.storage.local on service worker restart.
 */
async function restoreSessionState() {
  try {
    const result = await chrome.storage.local.get(['activeSession', 'currentActions']);
    if (result.activeSession && !result.activeSession.stoppedAt) {
      sessionManager.restoreSession(result.activeSession);
      actionStore.setActions(result.activeSession.actions || []);

      // Re-send START_RECORDING to the active tab so its content script
      // resumes capture after service worker restart.
      const activeTabId = sessionManager.getActiveTabId();
      if (activeTabId) {
        chrome.tabs.sendMessage(activeTabId, { kind: 'START_RECORDING' }).catch(() => { });
      }
    } else if (result.currentActions && result.currentActions.length > 0) {
      // Restore actions even if session is stopped (service worker restarted)
      actionStore.setActions(result.currentActions);
    }
  } catch {
    // Silently fail — if we can't restore, start fresh
  }
}

// Restore state on service worker startup
restoreSessionState();

// ─── Message Handling ───

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.kind) {
    case 'ACTION_CAPTURED': {
      // Task 3.3: Only accept actions from the recording tab (tab-scoping)
      const tabId = sender.tab ? sender.tab.id : null;
      if (tabId !== null && sessionManager.shouldCaptureAction(tabId)) {
        const entry = handleCapturedAction(message.action);
        // Relay to starting tab so page-level CDP consumers see cross-tab actions
        relayEntryToStartingTab(entry, [tabId]);
      }
      sendResponse({ success: true });
      break;
    }

    case 'PAGE_LOADED': {
      // Tell the content script whether it should be recording.
      // This handles: page navigation during recording, service worker restart,
      // and new tabs opened while recording.
      const pageTabId = sender.tab ? sender.tab.id : null;
      const shouldRecord = pageTabId !== null
        && sessionManager.isRecording()
        && sessionManager.getActiveTabId() === pageTabId;
      sendResponse({ success: true, shouldRecord });
      break;
    }

    case 'QUERY_RECORDING_STATUS': {
      // Content script asks for recording status (e.g. on visibilitychange).
      const queryTabId = sender.tab ? sender.tab.id : null;
      const tabShouldRecord = queryTabId !== null
        && sessionManager.isRecording()
        && sessionManager.getActiveTabId() === queryTabId;
      sendResponse({ shouldRecord: tabShouldRecord });
      break;
    }

    case 'START_RECORDING': {
      const tabId = message.tabId || (sender.tab ? sender.tab.id : null);
      const url = message.url || '';
      if (tabId) {
        (async () => {
          actionStore.clearAll();
          actionStore.setStartingTabId(tabId);
          await clearAllScreenshots();
          sessionManager.startRecording(tabId, url);
          actionStore.setActions(sessionManager.getActions());
          persistActiveSession(sessionManager.getSession());
          chrome.tabs.sendMessage(tabId, { kind: 'START_RECORDING' }).catch(() => { });
          sendResponse({ success: true, session: sessionManager.getSession() });
        })();
      } else {
        sendResponse({ success: true, session: sessionManager.getSession() });
      }
      return true;
    }

    case 'START_RECORDING_FROM_CDP': {
      const cdpTabId = sender.tab ? sender.tab.id : null;
      const cdpUrl = message.url || '';
      if (cdpTabId) {
        (async () => {
          actionStore.clearAll();
          actionStore.setStartingTabId(cdpTabId);
          await clearAllScreenshots();
          sessionManager.startRecording(cdpTabId, cdpUrl);
          actionStore.setActions(sessionManager.getActions());
          persistActiveSession(sessionManager.getSession());
          sendResponse({ success: true, session: sessionManager.getSession() });
        })();
      } else {
        sendResponse({ success: false, error: 'Could not determine tab ID' });
      }
      return true;
    }

    case 'STOP_RECORDING': {
      const tabId = sessionManager.getActiveTabId();
      const session = sessionManager.stopRecording();
      persistActiveSession(null);
      // Tell the content script to stop capturing events
      if (tabId) {
        chrome.tabs.sendMessage(tabId, { kind: 'STOP_RECORDING' }).catch(() => { });
      }
      // Serialize session for external consumption (removes large/redundant fields)
      const serializedSession = serializeRecording(session);
      sendResponse({ success: true, session: serializedSession });
      break;
    }

    case 'GET_STATE':
      sendResponse({
        isRecording: sessionManager.isRecording(),
        isPaused: sessionManager.isPaused(),
        activeTabId: sessionManager.getActiveTabId(),
        actions: actionStore.getActions(),
        session: sessionManager.getSession(),
      });
      break;

    case 'GET_RECORDING_FOR_EXPORT': {
      // Returns serialized recording suitable for external APIs (CDP, Bedrock, etc.)
      // Strips large/redundant fields like rawAction, collapsedActions, outerHTML, screenshots
      const session = sessionManager.getSession();
      const serializedSession = serializeRecording(session);
      sendResponse({
        success: true,
        recording: serializedSession,
      });
      break;
    }

    case 'REORDER_ACTION':
      actionStore.reorderAction(message.fromIndex, message.toIndex);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    case 'DELETE_ACTION': {
      const deletedAction = actionStore.getActions()[message.index];
      if (deletedAction) deleteScreenshot(deletedAction.id);
      actionStore.deleteAction(message.index);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;
    }

    case 'UPDATE_PROMPT':
      actionStore.updatePrompt(message.index, message.newPrompt);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    case 'CLEAR_ALL': {
      (async () => {
        actionStore.clearAll();
        await clearAllScreenshots();
        sessionManager.setActions(actionStore.getActionsRef());
        persistActiveSession(sessionManager.getSession());
        sendResponse({ success: true });
      })();
      return true;
    }

    // ─── Task 12: Export Script ───

    case 'EXPORT_SCRIPT': {
      const actions = actionStore.getActions();
      const session = sessionManager.getSession();
      let startingUrl = session ? session.startingUrl : '';
      // If session is stopped (null), derive startingUrl from the first navigation action
      if (!startingUrl && actions.length > 0 && actions[0].type === 'navigation') {
        startingUrl = actions[0].rawAction ? actions[0].rawAction.value : actions[0].url;
      }
      const startingTabId = session ? session.startingTabId : actionStore.getStartingTabId();
      const exportableSession = { startingUrl, startingTabId, actions };
      const script = scriptExporter.exportScript(exportableSession);
      sendResponse({ success: true, script });
      break;
    }

    // ─── Task 8: Intent Prompts ───

    case 'ADD_INTENT_PROMPT':
      actionStore.addIntentPrompt(message.atIndex, message.intentText);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    case 'COLLAPSE_TO_INTENT':
      actionStore.collapseToIntent(message.startIndex, message.endIndex, message.intentText);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    case 'EXPAND_INTENT':
      actionStore.expandIntent(message.index);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    // ─── Task 9: QA Assertions ───

    case 'ADD_ASSERTION':
      actionStore.addAssertion(message.actionIndex, message.assertion);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    case 'UPDATE_ASSERTION':
      actionStore.updateAssertion(message.actionIndex, message.assertionIndex, message.text);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    case 'DELETE_ASSERTION':
      actionStore.deleteAssertion(message.actionIndex, message.assertionIndex);
      sessionManager.setActions(actionStore.getActionsRef());
      persistActiveSession(sessionManager.getSession());
      sendResponse({ success: true, actions: actionStore.getActions() });
      break;

    // ─── Task 10: Storage Manager ───

    case 'SAVE_SESSION': {
      (async () => {
        try {
          let session = message.session || sessionManager.getSession();
          // If no active session (recording stopped), build one from current actions
          if (!session) {
            const actions = actionStore.getActions();
            if (actions.length === 0) {
              sendResponse({ success: false, error: 'No actions to save' });
              return;
            }
            const startingUrl = (actions[0].type === 'navigation' && actions[0].rawAction)
              ? actions[0].rawAction.value
              : actions[0].url || '';
            session = {
              id: crypto.randomUUID(),
              startedAt: actions[0].timestamp,
              stoppedAt: Date.now(),
              tabId: 0,
              startingUrl,
              name: message.sessionName || '',
              actions,
            };
          }
          if (message.sessionName && session) {
            session.name = message.sessionName;
          }
          await storageManager.saveSession(session);
          sendResponse({ success: true });
        } catch (e) {
          sendResponse({ success: false, error: e.message });
        }
      })();
      return true;
    }

    case 'LOAD_SESSION': {
      (async () => {
        try {
          const session = await storageManager.loadSession(message.sessionId);
          if (session) {
            actionStore.setActions(session.actions || []);
            sendResponse({ success: true, session });
          } else {
            sendResponse({ success: false, error: 'Session not found' });
          }
        } catch (e) {
          sendResponse({ success: false, error: e.message });
        }
      })();
      return true;
    }

    case 'DELETE_SESSION': {
      (async () => {
        try {
          await storageManager.deleteSession(message.sessionId);
          sendResponse({ success: true });
        } catch (e) {
          sendResponse({ success: false, error: e.message });
        }
      })();
      return true;
    }

    case 'LIST_SESSIONS': {
      (async () => {
        try {
          const sessions = await storageManager.listSessions();
          sendResponse({ success: true, sessions });
        } catch (e) {
          sendResponse({ success: false, error: e.message });
        }
      })();
      return true;
    }


    // ─── Screenshots for ZIP Export ───

    case 'GET_SCREENSHOTS': {
      (async () => {
        const screenshots = await getAllScreenshots();
        sendResponse({ success: true, screenshots });
      })();
      return true;
    }

    // ─── Run on Playground ───

    case 'RUN_ON_PLAYGROUND': {
      (async () => {
        try {
          // Generate the script
          const actions = actionStore.getActions();
          let startingUrl = '';
          const session = sessionManager.getSession();
          if (session) startingUrl = session.startingUrl;
          if (!startingUrl && actions.length > 0 && actions[0].type === 'navigation') {
            startingUrl = actions[0].rawAction ? actions[0].rawAction.value : actions[0].url;
          }

          // Build playground-specific payload: URL + just the action prompts
          const actionPrompts = actions
            .filter(a => a.type !== 'navigation' || actions.indexOf(a) !== 0) // skip initial nav
            .map(a => `nova.act("${a.prompt}")`)
            .join('\n');

          const playgroundUrl = 'https://nova.amazon.com/act?tab=playground';
          const forceNew = message.forceNewTab || false;
          let tab = null;

          // Try to reuse an existing playground tab unless forceNew is checked
          if (!forceNew) {
            const allTabs = await chrome.tabs.query({});
            tab = allTabs.find(t =>
              t.url && (
                t.url.includes('nova.amazon.com/act')
              )
            );
            if (tab) {
              // Focus the existing tab and reload it so the content script re-injects
              await chrome.tabs.update(tab.id, { active: true, url: playgroundUrl });
              await chrome.windows.update(tab.windowId, { focused: true });
            }
          }

          if (!tab) {
            // Open a new tab
            tab = await chrome.tabs.create({ url: playgroundUrl });
          }

          // Retry sending the message until the content script is ready
          const sendWithRetry = async (tabId, maxAttempts = 10, delay = 1500) => {
            for (let attempt = 0; attempt < maxAttempts; attempt++) {
              await new Promise(r => setTimeout(r, delay));
              try {
                await chrome.tabs.sendMessage(tabId, { kind: 'INJECT_SCRIPT', startingUrl, actionPrompts });
                return;
              } catch {
                // Content script not ready yet — retry
              }
            }
          };

          // Wait for tab to finish loading, then start retrying
          const waitForLoad = (tabId) => {
            chrome.tabs.onUpdated.addListener(function listener(updatedTabId, changeInfo) {
              if (updatedTabId === tabId && changeInfo.status === 'complete') {
                chrome.tabs.onUpdated.removeListener(listener);
                sendWithRetry(tabId);
              }
            });
          };

          waitForLoad(tab.id);

          sendResponse({ success: true });
        } catch (e) {
          sendResponse({ success: false, error: e.message });
        }
      })();
      return true;
    }

    default:
      break;
  }
  return false;
});

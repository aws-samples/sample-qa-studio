// Nova Act Recorder - Recording Serializer
// Prepares recording data for external consumption by removing large/redundant fields

'use strict';

/* eslint-disable no-unused-vars */

/**
 * @typedef {import('./types.js').ActionEntry} ActionEntry
 * @typedef {import('./types.js').ElementDescriptor} ElementDescriptor
 * @typedef {import('./types.js').Assertion} Assertion
 * @typedef {import('./types.js').RecordingSession} RecordingSession
 */

/**
 * Strips unnecessary fields from an ElementDescriptor for external consumption.
 * Removes: outerHTML, cssClasses, dataAttributes
 * @param {ElementDescriptor} element
 * @returns {Partial<ElementDescriptor>}
 * @private
 */
function stripElementDescriptor(element) {
  if (!element) return element;

  const { outerHTML: _outerHTML, cssClasses: _cssClasses, dataAttributes: _dataAttributes, ...rest } = element;
  return rest;
}

/**
 * Strips unnecessary fields from an ActionEntry for external consumption.
 * Removes: rawAction, collapsedActions, promptEdited
 * Also strips nested ElementDescriptor fields
 * @param {ActionEntry} action
 * @returns {Partial<ActionEntry>}
 * @private
 */
function stripActionEntry(action) {
  const { rawAction: _rawAction, collapsedActions: _collapsedActions, promptEdited: _promptEdited, ...rest } = action;

  // Strip nested element descriptor if present
  if (rest.element) {
    rest.element = stripElementDescriptor(rest.element);
  }

  return rest;
}

/**
 * Serializes a RecordingSession for external consumption (e.g., CDP stopRecording).
 * Strips large and redundant fields:
 * - ActionEntry: rawAction, collapsedActions, promptEdited
 * - ElementDescriptor: outerHTML, cssClasses, dataAttributes
 *
 * @param {RecordingSession} session - The recording session to serialize
 * @returns {Partial<RecordingSession>} The stripped session suitable for external consumption
 */
export function serializeRecording(session) {
  if (!session) return null;

  return {
    id: session.id,
    startedAt: session.startedAt,
    stoppedAt: session.stoppedAt,
    tabId: session.tabId,
    startingUrl: session.startingUrl,
    name: session.name,
    actions: session.actions.map(stripActionEntry),
  };
}

/**
 * Serializes an array of ActionEntry objects for external consumption.
 * Convenience method when you only have actions without a full session.
 *
 * @param {ActionEntry[]} actions - Array of actions to serialize
 * @returns {Partial<ActionEntry>[]} The stripped actions
 */
export function serializeActions(actions) {
  if (!actions) return [];
  return actions.map(stripActionEntry);
}

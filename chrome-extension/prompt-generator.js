// Nova Act Recorder - Prompt Generator
// Converts recorded actions into natural language prompts compatible with Nova Act SDK.

'use strict';

/**
 * @typedef {import('./types.js').ActionEntry} ActionEntry
 * @typedef {import('./types.js').RawAction} RawAction
 * @typedef {import('./types.js').MergeSuggestion} MergeSuggestion
 */

/**
 * PromptGenerator transforms ActionEntry objects into natural language prompt strings.
 */
export class PromptGenerator {
  /**
   * Generates a prompt string for a single ActionEntry.
   * - click → "click on '<Element_Descriptor>'"
   * - type → "type '<value>' into the '<Element_Descriptor>' field"
   * - change → "select '<value>' in '<Element_Descriptor>'" or "set '<Element_Descriptor>' to '<value>'"
   * - scroll → "scroll <direction>" or "scroll <direction> in the '<Element_Descriptor>'" for container scrolls
   * - navigation → "navigate to '<URL>'"
   * - intent → returns the user-provided intent text as-is
   * @param {ActionEntry} action
   * @returns {string}
   */
  generatePrompt(action) {
    if (action.type === 'intent') {
      return action.prompt;
    }

    const raw = action.rawAction;
    if (!raw) {
      return action.prompt || '';
    }

    switch (raw.type) {
      case 'click': {
        const desc = raw.element ? raw.element.text : 'element';
        if (raw.element && raw.element.associatedLabel) {
          const controlType = this._detectControlType(raw.element);
          if (controlType) {
            return `click on the '${raw.element.associatedLabel}' ${controlType}`;
          }
          return `click on '${raw.element.associatedLabel}'`;
        }
        return `click on '${desc}'`;
      }
      case 'type':
      case 'paste': {
        const desc = (raw.element && raw.element.associatedLabel) || (raw.element ? raw.element.text : 'field');
        const value = raw.value || '';
        if (!value) {
          return `clear the '${desc}' field`;
        }
        return `type '${value}' into the '${desc}' field`;
      }
      case 'change': {
        const desc = (raw.element && raw.element.associatedLabel) || (raw.element ? raw.element.text : 'field');
        const value = raw.value || '';
        // For select elements or checkboxes, use "select" or "check"
        if (raw.element && raw.element.tagName === 'select') {
          return `select '${value}' from the '${desc}' dropdown`;
        } else if (value === 'checked') {
          return `check the '${desc}' checkbox`;
        } else if (value === 'unchecked') {
          return `uncheck the '${desc}' checkbox`;
        } else {
          return `set '${desc}' to '${value}'`;
        }
      }
      case 'scroll': {
        const dir = raw.value || 'down';
        if (raw.scrollContainer) {
          return `scroll ${dir} in the '${raw.scrollContainer.text}'`;
        }
        return `scroll ${dir}`;
      }
      case 'navigation': {
        const url = raw.value || raw.url;
        return `navigate to '${url}'`;
      }
      case 'tab_switch': {
        const url = raw.value || raw.url;
        if (raw.tabTitle) {
          return `switch to tab '${raw.tabTitle}' (${url})`;
        }
        return `switch to tab at '${url}'`;
      }
      case 'extract_variable': {
        // Prefer the inferred extraction label (e.g., "Transit Time") over the element text
        // (which is often the value itself, e.g., "13.7 yrs / 3 days")
        if (raw.extractionLabel) {
          return raw.extractionLabel;
        }
        const desc = raw.element ? raw.element.text : 'element';
        return `the '${desc}'`;
      }
      default:
        return `perform ${raw.type}`;
    }
  }

  /**
   * Detects the control type from an element descriptor for use in prompts.
   * Returns "dropdown", "checkbox", etc. or undefined if no special type detected.
   * @param {import('./types.js').ElementDescriptor} element
   * @returns {string|undefined}
   * @private
   */
  _detectControlType(element) {
    const classes = (element.cssClasses || []).join(' ').toLowerCase();
    const ancestor = (element.ancestorPath || '').toLowerCase();
    const role = (element.attributes && element.attributes.role) || '';
    const tagName = (element.tagName || '').toLowerCase();

    if (classes.includes('dropdown') || ancestor.includes('dropdown')
      || role === 'combobox' || role === 'listbox') {
      return 'dropdown';
    }
    if (tagName === 'select') return 'dropdown';
    if (role === 'checkbox' || (element.attributes && element.attributes.type === 'checkbox')) return 'checkbox';
    if (role === 'radio' || (element.attributes && element.attributes.type === 'radio')) return 'radio';
    if (role === 'switch') return 'toggle';
    return undefined;
  }

  /**
   * Processes the full action log and returns an array of prompt strings.
   * @param {ActionEntry[]} actions
   * @returns {string[]}
   */
  generateAllPrompts(actions) {
    return actions.map(action => this.generatePrompt(action));
  }

  /**
   * Detects mergeable patterns in the action log and returns merge suggestions.
   * Patterns detected:
   * - type into search field + click search button → "search for '<value>'"
   * - type into field + click submit → "fill in '<field>' with '<value>' and submit"
   * @param {ActionEntry[]} actions
   * @returns {MergeSuggestion[]}
   */
  suggestMergedPrompts(actions) {
    /** @type {MergeSuggestion[]} */
    const suggestions = [];

    for (let i = 0; i < actions.length - 1; i++) {
      const current = actions[i];
      const next = actions[i + 1];

      // Handle type + click pairs
      if (current.type === 'type' && next.type === 'click') {
        if (!current.rawAction || !next.rawAction) continue;

        const inputValue = current.rawAction.value || '';
        const fieldDesc = current.rawAction.element ? current.rawAction.element.text : 'field';
        const clickDesc = next.rawAction.element ? next.rawAction.element.text.toLowerCase() : '';

        // Pattern: type into search field + click search button → "search for '<value>'"
        if (isSearchRelated(clickDesc) || isSearchRelated(fieldDesc)) {
          suggestions.push({
            startIndex: i,
            endIndex: i + 1,
            mergedPrompt: `search for '${inputValue}'`,
            reason: `type + click search = search for`,
          });
          continue;
        }

        // Pattern: type into field + click submit → "fill in '<field>' with '<value>' and submit"
        if (isSubmitRelated(clickDesc)) {
          suggestions.push({
            startIndex: i,
            endIndex: i + 1,
            mergedPrompt: `fill in '${fieldDesc}' with '${inputValue}' and submit`,
            reason: `type + click submit = fill and submit`,
          });
        }
      }
    }

    return suggestions;
  }
}

/**
 * Checks if a descriptor text is search-related.
 * @param {string} text
 * @returns {boolean}
 */
function isSearchRelated(text) {
  const lower = text.toLowerCase();
  return lower.includes('search') || lower.includes('find') || lower.includes('lookup');
}

/**
 * Checks if a descriptor text is submit-related.
 * @param {string} text
 * @returns {boolean}
 */
function isSubmitRelated(text) {
  const lower = text.toLowerCase();
  return lower.includes('submit') || lower.includes('send') || lower.includes('go') || lower.includes('ok') || lower.includes('confirm');
}

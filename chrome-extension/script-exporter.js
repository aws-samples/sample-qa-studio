// Nova Act Recorder - Script Exporter
// Generates complete Python scripts from recorded sessions using the Nova Act SDK.

'use strict';

/**
 * @typedef {import('./types.js').ExportableSession} ExportableSession
 * @typedef {import('./types.js').ActionEntry} ActionEntry
 * @typedef {import('./types.js').Assertion} Assertion
 */

/**
 * ScriptExporter generates a complete Python script from an ExportableSession.
 * The script uses the Nova Act SDK with `NovaAct` and `act()` calls.
 *
 * For multi-tab sessions, all unique tabs' `NovaAct` instances are opened at the
 * top of the script as nested `with` blocks, and all actions are emitted at the
 * innermost indentation level, switching between `nova_N` variables as the active
 * tab changes. Each unique browser tab maps 1-to-1 to a `nova_N` variable.
 */
export class ScriptExporter {
  /**
   * Generates a complete Python script from an ExportableSession.
   * @param {ExportableSession} session
   * @returns {string}
   */
  exportScript(session) {
    let actions = session.actions || [];
    let startingUrl = session.startingUrl || '';
    const startingTabId = session.startingTabId;

    // Use the first navigation action's URL as starting_page and skip it
    if (actions.length > 0 && actions[0].type === 'navigation') {
      const navUrl = actions[0].rawAction ? actions[0].rawAction.value : actions[0].url;
      if (navUrl) {
        startingUrl = navUrl;
      }
      actions = actions.slice(1);
    }

    // Merge consecutive scrolls into the next non-scroll action for export
    actions = this._mergeScrollActions(actions);

    // Check if this is a multi-tab session
    const hasTabSwitch = actions.some(a => a.type === 'tab_switch');

    // Analyze actions to determine which imports are needed
    const needsStringSchema = actions.some(a => a.type === 'extract_variable');
    const needsBoolSchema = actions.some(a => a.isIntent || (a.assertions && a.assertions.length > 0));

    const lines = [];

    // Imports
    lines.push('from nova_act import NovaAct');

    const schemaImports = [];
    if (needsStringSchema) schemaImports.push('STRING_SCHEMA');
    if (needsBoolSchema) schemaImports.push('BOOL_SCHEMA');
    if (schemaImports.length > 0) {
      lines.push(`from nova_act import ${schemaImports.join(', ')}`);
    }

    if (!hasTabSwitch) {
      // Single-tab: simple flat structure
      lines.push('');
      lines.push(`with NovaAct(starting_page="${this._escapeString(startingUrl)}") as nova:`);
      if (actions.length === 0) {
        lines.push('    pass');
      } else {
        for (const action of actions) {
          this._appendActionLines(lines, action, 'nova', 1);
        }
      }
    } else {
      // Multi-tab: nested with blocks using a tab stack
      this._generateMultiTab(lines, actions, startingUrl, startingTabId);
    }

    return lines.join('\n') + '\n';
  }

  /**
   * Generates nested `with` blocks for multi-tab sessions.
   *
   * Two-pass approach: first discovers all unique tabs, then opens all
   * `with` blocks at the top (nested) and emits all actions at the
   * innermost indentation level, switching `nova_N` variables as needed.
   *
   * @param {string[]} lines
   * @param {ActionEntry[]} actions
   * @param {string} startingUrl
   * @param {number} [startingTabId]
   * @private
   */
  _generateMultiTab(lines, actions, startingUrl, startingTabId) {
    const tabVarMap = new Map();
    let varCounter = 0;
    const assignVar = (tabId) => {
      if (tabVarMap.has(tabId)) return tabVarMap.get(tabId);
      varCounter++;
      tabVarMap.set(tabId, `nova_${varCounter}`);
      return tabVarMap.get(tabId);
    };

    // Pass 1: discover unique tabs and their starting URLs
    const firstTabId = startingTabId != null ? startingTabId : '__initial__';
    const tabOrder = [firstTabId];
    const tabUrls = new Map();
    tabUrls.set(firstTabId, startingUrl);
    assignVar(firstTabId);

    for (let i = 0; i < actions.length; i++) {
      if (actions[i].type !== 'tab_switch') continue;
      const rawTabId = actions[i].rawAction ? actions[i].rawAction.tabId : undefined;
      let url = actions[i].url || '';
      if (actions[i + 1] && actions[i + 1].type === 'navigation') {
        url = actions[i + 1].rawAction ? actions[i + 1].rawAction.value : actions[i + 1].url;
      }
      const switchTabId = rawTabId != null ? rawTabId : this._getUrlOrigin(url);
      if (!tabUrls.has(switchTabId)) {
        tabUrls.set(switchTabId, url);
        tabOrder.push(switchTabId);
        assignVar(switchTabId);
      }
    }

    // Emit nested with blocks (one per unique tab)
    lines.push('');
    for (let t = 0; t < tabOrder.length; t++) {
      const indent = '    '.repeat(t);
      const tabId = tabOrder[t];
      lines.push(`${indent}with NovaAct(starting_page="${this._escapeString(tabUrls.get(tabId))}") as ${tabVarMap.get(tabId)}:`);
    }

    // Pass 2: emit actions at innermost depth
    const depth = tabOrder.length;
    let currentTabId = firstTabId;
    let hasActions = false;

    for (let i = 0; i < actions.length; i++) {
      const action = actions[i];
      if (action.type === 'tab_switch') {
        const rawTabId = action.rawAction ? action.rawAction.tabId : undefined;
        currentTabId = rawTabId != null ? rawTabId : this._getUrlOrigin(action.url || '');
        if (actions[i + 1] && actions[i + 1].type === 'navigation') i++;
      } else {
        this._appendActionLines(lines, action, tabVarMap.get(currentTabId), depth);
        hasActions = true;
      }
    }

    if (!hasActions) {
      lines.push(`${'    '.repeat(depth)}pass`);
    }
  }

  /**
   * Extracts the origin (scheme + host) from a URL for tab identity matching.
   * Used as fallback when Chrome tabId is not available.
   * @param {string} url
   * @returns {string}
   * @private
   */
  _getUrlOrigin(url) {
    const match = url.match(/^(https?:\/\/[^/]+)/);
    return match ? match[1] : url;
  }

  /**
   * Appends Python lines for a single action entry.
   * @param {string[]} lines
   * @param {ActionEntry} action
   * @param {string} novaVar - The nova variable name
   * @param {number} depth - Nesting depth (1 = 4 spaces, 2 = 8 spaces, etc.)
   * @private
   */
  _appendActionLines(lines, action, novaVar, depth) {
    const indent = '    '.repeat(depth);
    const prompt = action.prompt || '';

    if (action.type === 'extract_variable') {
      const varName = action.variableName || 'var';
      lines.push(`${indent}${varName} = ${novaVar}.act_get("${this._escapeString(prompt)}", schema=STRING_SCHEMA)`);
      return;
    }

    // Intent prompts → act_get with BOOL_SCHEMA + assert
    if (action.isIntent) {
      lines.push(`${indent}result = ${novaVar}.act_get("${this._escapeString(prompt)}", schema=BOOL_SCHEMA)`);
      lines.push(`${indent}assert result.parsed_response, "${this._escapeString(prompt)}"`);
      return;
    }

    if (action.type === 'paste' && action.sourceVariableName && !action.promptEdited) {
      const rawEl = action.rawAction && action.rawAction.element;
      const desc = rawEl ? (rawEl.associatedLabel || rawEl.text) : 'field';
      const safeDesc = this._escapeString(desc).replace(/\{/g, '{{').replace(/\}/g, '}}');
      lines.push(`${indent}${novaVar}.act(f"type '{${action.sourceVariableName}}' into the '${safeDesc}' field")`);
    } else {
      lines.push(`${indent}${novaVar}.act("${this._escapeString(prompt)}")`);
    }

    // Assertions
    if (action.assertions && action.assertions.length > 0) {
      for (const assertion of action.assertions) {
        const assertionText = assertion.text || '';
        lines.push(`${indent}result = ${novaVar}.act_get("${this._escapeString(assertionText)}", schema=BOOL_SCHEMA)`);
        lines.push(`${indent}assert result.parsed_response, "${this._escapeString(assertionText)}"`);
      }
    }
  }

  /**
   * Merges consecutive scroll actions for export: only the last scroll in a
   * consecutive run survives, and its prompt is prepended to the next
   * non-scroll action (e.g. "scroll down and click on 'Submit' button").
   * Scrolls are NOT merged across tab switches or navigations.
   * Trailing scrolls with no following action are kept standalone.
   * @param {ActionEntry[]} actions
   * @returns {ActionEntry[]}
   * @private
   */
  _mergeScrollActions(actions) {
    const result = [];
    let pendingScroll = null;

    for (const action of actions) {
      if (action.type === 'scroll') {
        // Last scroll wins — replace any earlier pending scroll
        pendingScroll = action;
      } else if (action.type === 'tab_switch' || action.type === 'navigation') {
        // Flush pending scroll standalone before boundary actions
        if (pendingScroll) {
          result.push(pendingScroll);
          pendingScroll = null;
        }
        result.push(action);
      } else {
        if (pendingScroll) {
          const scrollPrompt = pendingScroll.prompt || '';
          result.push({ ...action, prompt: `${scrollPrompt} and ${action.prompt}` });
          pendingScroll = null;
        } else {
          result.push(action);
        }
      }
    }

    if (pendingScroll) {
      result.push(pendingScroll);
    }

    return result;
  }

  /**
   * Escapes a string for use inside a Python double-quoted string.
   * @param {string} str
   * @returns {string}
   * @private
   */
  _escapeString(str) {
    return str
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '\\"')
      .replace(/\n/g, '\\n')
      .replace(/\r/g, '\\r')
      .replace(/\t/g, '\\t');
  }
}

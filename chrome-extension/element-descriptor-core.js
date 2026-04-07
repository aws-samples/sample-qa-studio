// Nova Act Recorder - Element Descriptor Extraction (Core Logic)
// Plain script loaded by Chrome via manifest.json before content.js.
// Functions defined here are available as globals to content.js.
// The ES module wrapper (element-descriptor.js) re-exports these for tests and background.js.

'use strict';

/**
 * Extracts a human-readable ElementDescriptor from a DOM element.
 * Priority: visible text > aria-label > role+position > placeholder > name > id > tagName+position
 * @param {Element} element
 * @returns {import('./types.js').ElementDescriptor}
 */
function extractElementDescriptor(element) {
  const tagName = element.tagName.toLowerCase();
  const attributes = {
    id: element.id || undefined,
    ariaLabel: element.getAttribute('aria-label') || undefined,
    role: element.getAttribute('role') || undefined,
    placeholder: element.getAttribute('placeholder') || undefined,
    name: element.getAttribute('name') || undefined,
    type: element.getAttribute('type') || undefined,
    href: element.getAttribute('href') || undefined,
    src: element.getAttribute('src') || undefined,
    alt: element.getAttribute('alt') || undefined,
    value: element.value !== undefined && element.value !== '' ? element.value : undefined,
  };

  let text = '';

  // 1. Visible text content (trimmed, max 80 chars)
  const visibleText = getVisibleText(element);
  if (visibleText) {
    text = visibleText.substring(0, 80);
  }
  // 2. aria-label
  else if (attributes.ariaLabel) {
    text = attributes.ariaLabel;
  }
  // 3. role + position
  else if (attributes.role) {
    const position = getNthChildPosition(element);
    text = `${attributes.role} (${position})`;
  }
  // 4. placeholder
  else if (attributes.placeholder) {
    text = attributes.placeholder;
  }
  // 5. name attribute
  else if (attributes.name) {
    text = attributes.name;
  }
  // 6. id attribute
  else if (attributes.id) {
    text = attributes.id;
  }
  // 7. Fallback: tagName + nth-child position
  else {
    const position = getNthChildPosition(element);
    text = `${tagName}:nth-child(${position})`;
  }

  // CSS classes
  const cssClasses = element.classList
    ? Array.from(element.classList).filter(c => c.length > 0)
    : [];

  // data-* attributes
  const dataAttributes = {};
  if (element.dataset) {
    for (const key of Object.keys(element.dataset)) {
      dataAttributes[key] = element.dataset[key];
    }
  }

  // Outer HTML (truncated to 500 chars)
  const outerHTML = element.outerHTML
    ? element.outerHTML.substring(0, 500)
    : undefined;

  // Ancestor path (up to 4 levels)
  const ancestorPath = getAncestorPath(element, 4);

  // Associated label (for form controls)
  const associatedLabel = getAssociatedLabel(element);

  // Nearest heading above the element
  const nearestHeading = getNearestHeading(element);

  const descriptor = { text, tagName, attributes };
  if (cssClasses.length > 0) descriptor.cssClasses = cssClasses;
  if (Object.keys(dataAttributes).length > 0) descriptor.dataAttributes = dataAttributes;
  if (outerHTML) descriptor.outerHTML = outerHTML;
  if (ancestorPath) descriptor.ancestorPath = ancestorPath;
  if (associatedLabel) descriptor.associatedLabel = associatedLabel;
  if (nearestHeading) descriptor.nearestHeading = nearestHeading;

  return descriptor;
}

/**
 * Gets visible text content from an element, excluding input-like elements.
 * @param {Element} element
 * @returns {string}
 */
function getVisibleText(element) {
  if (element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA') {
    return '';
  }
  const text = (element.textContent || '').replace(/\s+/g, ' ').trim();
  return text;
}

/**
 * Gets the 1-based nth-child position of an element among its siblings of the same tag.
 * @param {Element} element
 * @returns {number}
 */
function getNthChildPosition(element) {
  if (!element.parentElement) return 1;
  const siblings = Array.from(element.parentElement.children);
  const sameTagSiblings = siblings.filter(s => s.tagName === element.tagName);
  return sameTagSiblings.indexOf(element) + 1;
}

/**
 * Builds a short ancestor path string like "nav > ul.menu > li.active".
 * Walks up to `maxDepth` parent elements, including tag + classes for each.
 * @param {Element} element
 * @param {number} maxDepth
 * @returns {string|undefined}
 */
function getAncestorPath(element, maxDepth) {
  const parts = [];
  let current = element.parentElement;
  let depth = 0;
  while (current && depth < maxDepth) {
    const tag = current.tagName ? current.tagName.toLowerCase() : '';
    if (!tag || tag === 'html' || tag === 'body') break;
    const classes = current.classList
      ? Array.from(current.classList).filter(c => c.length > 0).slice(0, 3).join('.')
      : '';
    parts.unshift(classes ? `${tag}.${classes}` : tag);
    current = current.parentElement;
    depth++;
  }
  return parts.length > 0 ? parts.join(' > ') : undefined;
}

/**
 * Finds the associated <label> text for a form control.
 * Checks for a wrapping <label> or one linked via the `for` attribute.
 * @param {Element} element
 * @returns {string|undefined}
 */
function getAssociatedLabel(element) {
  // Check for wrapping <label>
  if (element.closest) {
    const wrappingLabel = element.closest('label');
    if (wrappingLabel) {
      const labelText = (wrappingLabel.textContent || '').replace(/\s+/g, ' ').trim();
      if (labelText) return labelText.substring(0, 120);
    }
  }

  // Check for label[for="id"]
  if (element.id && element.ownerDocument) {
    const linkedLabel = element.ownerDocument.querySelector(`label[for="${element.id}"]`);
    if (linkedLabel) {
      const labelText = (linkedLabel.textContent || '').replace(/\s+/g, ' ').trim();
      if (labelText) return labelText.substring(0, 120);
    }
  }

  // Check for sibling <label> in the same parent with a clear 1:1 mapping
  const siblingLabel = _findSiblingLabelForInput(element);
  if (siblingLabel) return siblingLabel;

  return undefined;
}

/**
 * Finds a <label> in a parent form-field group by walking up the ancestor chain.
 * At each level, checks if the ancestor has exactly one <label> child and a small
 * number of other children (indicating a tight form-field group, not a large form).
 * Handles patterns like:
 *   <div class="form-field"><label>Name</label><input></div>
 *   <div class="form-field"><label>Relationship</label><div class="dropdown"><button>...</button></div></div>
 * @param {Element} element
 * @returns {string|undefined}
 */
function _findSiblingLabelForInput(element) {
  let current = element;
  for (let depth = 0; depth < 4; depth++) {
    const parent = current.parentElement;
    if (!parent || parent.tagName === 'BODY' || parent.tagName === 'HTML' || parent.tagName === 'FORM') break;

    // Stop at menu/popup boundaries — items inside these are choices, not labeled fields
    if (_isMenuContainer(parent)) break;

    const labels = Array.from(parent.children).filter(el => el.tagName === 'LABEL');
    if (labels.length === 1) {
      const nonLabelChildren = Array.from(parent.children).filter(el => el.tagName !== 'LABEL');
      // A form-field group typically has 1-3 non-label children (the control, maybe a helper text)
      if (nonLabelChildren.length >= 1 && nonLabelChildren.length <= 3) {
        const labelText = (labels[0].textContent || '').trim();
        if (labelText && labelText.length <= 120) return labelText;
      }
    }

    current = parent;
  }
  return undefined;
}

/**
 * Checks if an element is a menu/popup container whose children are selectable items
 * rather than labeled form fields.
 * @param {Element} element
 * @returns {boolean}
 */
function _isMenuContainer(element) {
  const role = element.getAttribute ? (element.getAttribute('role') || '') : '';
  if (['menu', 'listbox', 'dialog', 'tooltip'].includes(role)) return true;

  const classes = element.classList
    ? Array.from(element.classList).join(' ').toLowerCase()
    : '';
  return classes.includes('dropdown-menu') || classes.includes('popover') || classes.includes('popup');
}

/**
 * Finds the nearest heading (h1-h6) above the element in the DOM.
 * Walks backward through previous siblings and ancestors.
 * @param {Element} element
 * @returns {string|undefined}
 */
function getNearestHeading(element) {
  const headingTags = new Set(['H1', 'H2', 'H3', 'H4', 'H5', 'H6']);

  // Walk backward through previous siblings, then up to parent
  let current = element;
  let depth = 0;
  while (current && depth < 10) {
    // Check previous siblings
    let sibling = current.previousElementSibling;
    while (sibling) {
      if (headingTags.has(sibling.tagName)) {
        const text = (sibling.textContent || '').trim();
        if (text) return text.substring(0, 120);
      }
      sibling = sibling.previousElementSibling;
    }
    // Check the current element's parent itself
    current = current.parentElement;
    if (current && headingTags.has(current.tagName)) {
      const text = (current.textContent || '').trim();
      if (text) return text.substring(0, 120);
    }
    depth++;
  }
  return undefined;
}

/**
 * Consolidates a sequence of keystrokes into a single typing action value.
 * Given a sequence of input events on the same element, returns the final value.
 * @param {string[]} keystrokes - Array of intermediate values or the final value
 * @returns {string} The final consolidated value
 */
function consolidateTyping(keystrokes) {
  if (!keystrokes || keystrokes.length === 0) return '';
  return keystrokes[keystrokes.length - 1];
}

// Expose for ES module re-export (element-descriptor.js).
// In Chrome content scripts, functions are already globals via shared scope.
if (typeof globalThis !== 'undefined') {
  globalThis.__elementDescriptorExports = {
    extractElementDescriptor,
    getVisibleText,
    getNthChildPosition,
    getAncestorPath,
    getAssociatedLabel,
    getNearestHeading,
    consolidateTyping,
  };
}

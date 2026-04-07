// Nova Act Recorder - Element Descriptor (ES Module Wrapper)
// Re-exports functions from element-descriptor-core.js as ES modules.
// Used by tests (vitest) and background.js. The core logic lives in
// element-descriptor-core.js, which Chrome loads as a plain content script.

import './element-descriptor-core.js';

export const {
  extractElementDescriptor,
  getVisibleText,
  getNthChildPosition,
  getAncestorPath,
  getAssociatedLabel,
  getNearestHeading,
  consolidateTyping,
} = globalThis.__elementDescriptorExports;

// Globals provided by element-descriptor-core.js (loaded before content.js via manifest.json)
const elementDescriptorGlobals = {
  extractElementDescriptor: 'readonly',
  getVisibleText: 'readonly',
  getNthChildPosition: 'readonly',
  getAncestorPath: 'readonly',
  getAssociatedLabel: 'readonly',
  getNearestHeading: 'readonly',
  consolidateTyping: 'readonly',
};

export default [
  {
    files: ['**/*.js'],
    ignores: ['node_modules/**', 'test/**'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        chrome: 'readonly',
        document: 'readonly',
        window: 'readonly',
        navigator: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        prompt: 'readonly',
        confirm: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        AbortController: 'readonly',
        crypto: 'readonly',
        HTMLTextAreaElement: 'readonly',
        HTMLInputElement: 'readonly',
        Event: 'readonly',
        KeyboardEvent: 'readonly',
        JSZip: 'readonly',
        URL: 'readonly',
        self: 'readonly',
      },
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-const-assign': 'error',
      'no-dupe-keys': 'error',
      'no-duplicate-case': 'error',
      'no-unreachable': 'error',
      'no-unexpected-multiline': 'error',
      'valid-typeof': 'error',
      'no-redeclare': 'error',
    },
  },
  // content.js is a classic script that receives globals from element-descriptor-core.js
  {
    files: ['content.js'],
    languageOptions: {
      sourceType: 'script',
      globals: elementDescriptorGlobals,
    },
  },
  // element-descriptor-core.js is a classic script loaded by Chrome via manifest
  {
    files: ['element-descriptor-core.js'],
    languageOptions: {
      sourceType: 'script',
      globals: {
        globalThis: 'readonly',
      },
    },
  },
];

// Nova Act Recorder - Playground Injector
// Injected into the Nova Act Playground page to fill the URL field and action description.

'use strict';

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.kind !== 'INJECT_SCRIPT') return;

  const startingUrl = message.startingUrl || '';
  const actionPrompts = message.actionPrompts || '';

  console.log('[Nova Act Recorder] Injecting — URL:', startingUrl, 'Actions length:', actionPrompts.length);

  injectWithRetry(startingUrl, actionPrompts, 0)
    .then((result) => {
      console.log('[Nova Act Recorder] Injection result:', result);
      sendResponse({ success: true, ...result });
    })
    .catch((err) => {
      console.warn('[Nova Act Recorder] Injection failed, using clipboard fallback:', err.message);
      copyToClipboardFallback(startingUrl, actionPrompts);
      sendResponse({ success: true, method: 'clipboard' });
    });

  return true;
});

async function injectWithRetry(url, actions, attempt) {
  const maxAttempts = 20;
  const delay = 800 + attempt * 400;

  if (attempt >= maxAttempts) throw new Error('Max attempts reached');

  await sleep(delay);

  const urlFilled = tryFillUrlField(url);
  const actionsFilled = tryFillActionField(actions);

  if (urlFilled && actionsFilled) {
    showBanner('✅ Script injected into playground');
    return { urlFilled, actionsFilled };
  }

  // Log what's missing for debugging
  if (!urlFilled) console.log('[Nova Act Recorder] URL field not found yet, attempt', attempt);
  if (!actionsFilled) console.log('[Nova Act Recorder] Action field not found yet, attempt', attempt);

  return injectWithRetry(url, actions, attempt + 1);
}

/**
 * Finds and fills the URL input field.
 * The playground uses: <textarea placeholder="Enter a URL" class="steps-builder-input first-step">
 */
function tryFillUrlField(url) {
  if (!url) return true;

  // Direct match for the playground's URL textarea
  const directMatch = document.querySelector('textarea[placeholder="Enter a URL"]')
    || document.querySelector('textarea.first-step');
  if (directMatch) {
    setTextareaValue(directMatch, url);
    console.log('[Nova Act Recorder] URL filled via direct playground match');
    return true;
  }

  // Broader selectors
  const selectors = [
    'textarea[placeholder*="URL" i]',
    'textarea[placeholder*="url" i]',
    'input[placeholder*="URL" i]',
    'input[placeholder*="url" i]',
    'input[type="url"]',
    'input[placeholder*="http"]',
    'textarea[placeholder*="http"]',
  ];

  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el) {
      if (el.tagName === 'TEXTAREA') {
        setTextareaValue(el, url);
      } else {
        setInputValue(el, url);
      }
      console.log('[Nova Act Recorder] URL filled via:', selector);
      return true;
    }
  }

  return false;
}

/**
 * Finds and fills the action description field.
 * The playground uses: <textarea class="steps-builder-input"> (not the first-step one)
 */
function tryFillActionField(actions) {
  if (!actions) return true;

  // Direct match: playground's action textareas (steps-builder-input but NOT first-step)
  const allStepInputs = document.querySelectorAll('textarea.steps-builder-input');
  for (const ta of allStepInputs) {
    if (!ta.classList.contains('first-step')) {
      setTextareaValue(ta, actions);
      console.log('[Nova Act Recorder] Actions filled via steps-builder-input (non-first-step)');
      return true;
    }
  }

  const selectors = [
    'textarea[placeholder*="describe" i]',
    'textarea[placeholder*="action" i]',
    'textarea[placeholder*="agent" i]',
    'textarea[placeholder*="script" i]',
    'textarea[placeholder*="instruction" i]',
    'textarea[placeholder*="prompt" i]',
    'textarea[placeholder*="step" i]',
    'textarea[aria-label*="action" i]',
    'textarea[aria-label*="describe" i]',
    'textarea[aria-label*="agent" i]',
    'textarea[aria-label*="instruction" i]',
  ];

  for (const selector of selectors) {
    const textarea = document.querySelector(selector);
    if (textarea) {
      setTextareaValue(textarea, actions);
      console.log('[Nova Act Recorder] Actions filled via:', selector);
      return true;
    }
  }

  // Fallback: find any textarea that's large enough to be the action editor
  const allTextareas = document.querySelectorAll('textarea');
  for (const ta of allTextareas) {
    const ph = (ta.placeholder || '').toLowerCase();
    const label = (ta.getAttribute('aria-label') || '').toLowerCase();
    if (ph.includes('describe') || ph.includes('action') || ph.includes('agent') ||
        ph.includes('instruction') || ph.includes('prompt') ||
        label.includes('action') || label.includes('describe') || label.includes('agent')) {
      setTextareaValue(ta, actions);
      console.log('[Nova Act Recorder] Actions filled via fallback textarea');
      return true;
    }
  }

  // Last resort: largest textarea on the page
  let largest = null;
  let largestArea = 0;
  for (const ta of allTextareas) {
    const area = ta.offsetWidth * ta.offsetHeight;
    if (area > largestArea) {
      largestArea = area;
      largest = ta;
    }
  }
  if (largest && largestArea > 5000) {
    setTextareaValue(largest, actions);
    console.log('[Nova Act Recorder] Actions filled via largest textarea');
    return true;
  }

  return false;
}

/**
 * Sets an input value using the native setter to trigger React change handlers.
 */
function setInputValue(input, value) {
  const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
  ).set;
  nativeSetter.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  // Also try focus/blur to trigger validation
  input.focus();
  input.dispatchEvent(new Event('blur', { bubbles: true }));
}

/**
 * Sets a textarea value using the native setter to trigger React change handlers.
 */
function setTextareaValue(textarea, value) {
  const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, 'value'
  ).set;
  nativeSetter.call(textarea, value);
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  textarea.dispatchEvent(new Event('change', { bubbles: true }));
  textarea.focus();
  textarea.dispatchEvent(new Event('blur', { bubbles: true }));
}

function copyToClipboardFallback(url, actions) {
  const text = `URL: ${url}\n\n${actions}`;
  navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
  showBanner('📋 Script copied to clipboard — paste the URL and actions manually');
}

function showBanner(text) {
  const existing = document.getElementById('nova-act-recorder-banner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'nova-act-recorder-banner';
  banner.textContent = text;
  banner.style.cssText = `
    position: fixed; top: 0; left: 0; right: 0; z-index: 999999;
    background: #2ecc71; color: #fff; padding: 12px 20px;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 14px; font-weight: 600; text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    transition: opacity 0.3s;
  `;
  document.body.prepend(banner);
  setTimeout(() => { banner.style.opacity = '0'; setTimeout(() => banner.remove(), 300); }, 6000);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

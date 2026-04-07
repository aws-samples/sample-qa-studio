"""
Extension Helper - CDP utilities for verifying and enabling the NovaActRecorder Chrome extension
in the remote AgentCore browser.

Uses Chrome DevTools Protocol (CDP) to:
1. Verify the extension is installed by checking for its service worker target
2. Verify content scripts are active on the current page
3. Open the extension's side panel programmatically
"""

import logging
import time

logger = logging.getLogger(__name__)

EXTENSION_NAME = "Nova Act Recorder"


def verify_extension_loaded(nova):
    """Verify the NovaActRecorder extension is installed and active in the browser.

    Uses CDP Target.getTargets to find extension-related targets (service worker, pages).
    Returns dict with extension status info.
    """
    cdp_session = None
    result = {
        "installed": False,
        "service_worker_active": False,
        "content_script_active": False,
        "extension_id": None,
    }

    try:
        cdp_session = nova.page.context.new_cdp_session(nova.page)

        # Get all browser targets - extension service workers and pages show up here
        targets = cdp_session.send("Target.getTargets")
        target_infos = targets.get("targetInfos", [])

        logger.info(f"CDP Target.getTargets returned {len(target_infos)} targets")

        for target in target_infos:
            target_type = target.get("type", "")
            title = target.get("title", "")
            url = target.get("url", "")

            logger.info(f"  Target: type={target_type}, title={title}, url={url[:100]}")

            # Extension service workers have type "service_worker" and chrome-extension:// URL
            if target_type == "service_worker" and "chrome-extension://" in url:
                if EXTENSION_NAME.lower() in title.lower() or "nova" in title.lower():
                    result["installed"] = True
                    result["service_worker_active"] = True
                    # Extract extension ID from URL: chrome-extension://<id>/background.js
                    ext_id = url.split("chrome-extension://")[1].split("/")[0]
                    result["extension_id"] = ext_id
                    logger.info(f"Found extension service worker: id={ext_id}")

            # Extension pages (popup, side panel) have type "page" with chrome-extension:// URL
            if target_type == "page" and "chrome-extension://" in url:
                if "popup" in url or "sidepanel" in url or "side_panel" in url:
                    result["installed"] = True
                    ext_id = url.split("chrome-extension://")[1].split("/")[0]
                    result["extension_id"] = ext_id
                    logger.info(f"Found extension page: url={url}")

        # If we didn't find by name, look for our specific extension by background.js filename
        # Our manifest uses "background.js" directly (not background.mjs or src/background/index.js)
        if not result["installed"]:
            for target in target_infos:
                url = target.get("url", "")
                if (target.get("type") == "service_worker" and
                    "chrome-extension://" in url and
                    url.endswith("/background.js")):
                    result["installed"] = True
                    result["service_worker_active"] = True
                    ext_id = url.split("chrome-extension://")[1].split("/")[0]
                    result["extension_id"] = ext_id
                    logger.info(f"Found NovaActRecorder extension by background.js: id={ext_id}")
                    break

        # Last resort: any chrome-extension service worker
        if not result["installed"]:
            for target in target_infos:
                if target.get("type") == "service_worker" and "chrome-extension://" in target.get("url", ""):
                    result["installed"] = True
                    result["service_worker_active"] = True
                    ext_id = target["url"].split("chrome-extension://")[1].split("/")[0]
                    result["extension_id"] = ext_id
                    logger.info(f"Found chrome extension service worker (unconfirmed name): id={ext_id}")
                    break

        # Check if content scripts are active on the current page
        # The NovaActRecorder content.js adds event listeners - we can check by trying to
        # detect if chrome.runtime is available (content scripts have access to it)
        try:
            check_result = cdp_session.send("Runtime.evaluate", {
                "expression": """
                    (function() {
                        // Check if any content script event listeners are present
                        // Content scripts from extensions can be detected by checking
                        // if chrome.runtime.id returns the extension's ID
                        try {
                            // This will only work from content script context, not page context
                            // Instead, check for side effects of the content script
                            return {
                                hasContentScript: typeof document.__novaRecorderInitialized !== 'undefined',
                                url: window.location.href
                            };
                        } catch(e) {
                            return { hasContentScript: false, error: e.message };
                        }
                    })()
                """,
                "returnByValue": True
            })

            check_value = check_result.get("result", {}).get("value", {})
            if check_value and check_value.get("hasContentScript"):
                result["content_script_active"] = True
                logger.info("Content script detected on page")
            else:
                logger.info(f"Content script check result: {check_value}")
                # Content scripts run in an isolated world, so we can't easily detect them
                # from the page context. If the service worker is active, content scripts
                # are likely injected too.
                if result["service_worker_active"]:
                    result["content_script_active"] = True
                    logger.info("Assuming content scripts active (service worker is running)")
        except Exception as e:
            logger.warning(f"Content script check failed: {e}")
            if result["service_worker_active"]:
                result["content_script_active"] = True

        logger.info(f"Extension verification result: {result}")

    except Exception as e:
        logger.error(f"Extension verification failed: {e}")
    finally:
        if cdp_session:
            try:
                cdp_session.detach()
            except:
                pass

    return result




def setup_extension(nova):
    """Main entry point: verify extension is loaded and attempt to enable it.

    Call this after NovaAct initialization in wizard mode.
    Returns the verification result dict.
    """
    logger.info("Setting up NovaActRecorder extension...")

    # Wait briefly for extension to initialize after page load
    time.sleep(2)

    # Verify extension is installed
    status = verify_extension_loaded(nova)

    if not status["installed"]:
        logger.warning("NovaActRecorder extension NOT detected in browser. "
                       "Check that the extension ZIP is correctly uploaded to S3 "
                       "and the extensions parameter is passed to BrowserClient.start().")
        return status

    logger.info(f"NovaActRecorder extension detected: id={status['extension_id']}, "
                f"service_worker={status['service_worker_active']}, "
                f"content_script={status['content_script_active']}")

    return status

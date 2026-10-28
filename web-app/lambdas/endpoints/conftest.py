"""
Conftest for endpoint Lambda tests.

Stubs out lambda_init so the Linux ARM64 dependencies/ folder
(installed for Lambda deployment) is never added to sys.path on macOS.
System-installed packages (pydantic, etc.) are used instead.

Also adds the auth directory to sys.path so shared modules (role_scopes)
are importable — in the Lambda deployment, all layers are flattened.
"""
import os
import sys
import types

# Pre-register a no-op lambda_init module before any test imports it
sys.modules.setdefault("lambda_init", types.ModuleType("lambda_init"))

# Add the auth directory to sys.path so role_scopes is importable
_AUTH_DIR = os.path.join(os.path.dirname(__file__), '..', 'auth')
if os.path.abspath(_AUTH_DIR) not in sys.path:
    sys.path.insert(0, os.path.abspath(_AUTH_DIR))

"""
Conftest for endpoint Lambda tests.

Stubs out lambda_init so the Linux ARM64 dependencies/ folder
(installed for Lambda deployment) is never added to sys.path on macOS.
System-installed packages (pydantic, etc.) are used instead.
"""
import sys
import types

# Pre-register a no-op lambda_init module before any test imports it
sys.modules.setdefault("lambda_init", types.ModuleType("lambda_init"))

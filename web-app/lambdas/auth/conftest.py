"""Stub lambda_init so tests don't load Linux ARM64 dependencies on macOS."""
import sys
import types

sys.modules.setdefault("lambda_init", types.ModuleType("lambda_init"))

"""Template parser for {{variable}} substitution in step instructions.

Mirrors the worker's ``TemplateParser`` (``web-app/worker/template_parser.py``)
so the CLI and the cloud worker resolve templates identically (R-PARITY-2).

The CLI operates on plain dicts for user variables and runtime variables
(whereas the worker uses an ``ExecutionVariables`` dataclass).  This class
accepts dicts directly and exposes the same substitution semantics:

- ``{{UniqueID}}`` — 5-char random alphanumeric, generated once per parser.
- ``{{Time}}``     — ``%Y-%m-%dT%H:%M:%SZ`` UTC-ish snapshot at parser creation.
- ``{{ExecutionID}}``
- ``{{CreatedAt}}``

Built-ins cannot be overridden by user variables or runtime variables —
``add_runtime_variable`` raises ``ValueError`` on collision.

Runtime variables take precedence over user-defined variables of the same
name (matches the worker's dict-rebuild order).

The implementation is intentionally plain ``str.replace`` to match the
worker — Go-template syntax was the original spec.
"""

from __future__ import annotations

import random
import string
from datetime import datetime
from typing import Dict, Optional


_BUILTIN_NAMES = frozenset({"UniqueID", "Time", "ExecutionID", "CreatedAt"})


class TemplateParser:
    """Resolve ``{{var}}`` placeholders in strings."""

    def __init__(
        self,
        execution_id: str = "",
        created_at: str = "",
        variables: Optional[Dict[str, str]] = None,
        runtime_variables: Optional[Dict[str, str]] = None,
    ) -> None:
        self.execution_id = execution_id
        self.created_at = created_at
        self._user_variables: Dict[str, str] = dict(variables or {})
        self._runtime_variables: Dict[str, str] = dict(runtime_variables or {})
        self._builtins: Dict[str, str] = {
            "UniqueID": self._generate_unique_id(),
            "Time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ExecutionID": execution_id,
            "CreatedAt": created_at,
        }

    # ------------------------------------------------------------------
    # Substitution
    # ------------------------------------------------------------------

    def parse_instruction(self, text: str) -> str:
        """Replace every ``{{key}}`` in ``text`` with the resolved value.

        Lookup order: built-ins > runtime variables > user variables.
        Unknown placeholders are left untouched.
        """
        if not text:
            return text
        parsed = text
        for key, value in self._merged_variables().items():
            parsed = parsed.replace(f"{{{{{key}}}}}", str(value))
        return parsed

    # ------------------------------------------------------------------
    # Runtime-variable management
    # ------------------------------------------------------------------

    def add_runtime_variable(self, key: str, value: str) -> None:
        """Add or update a runtime variable.

        Raises ``ValueError`` when ``key`` is empty, not a string, or would
        shadow a built-in. Mirrors the worker's validation.
        """
        if not key or not isinstance(key, str):
            raise ValueError(f"Invalid variable name: {key!r}")
        if key in _BUILTIN_NAMES:
            raise ValueError(f"Cannot override built-in variable: {key}")
        self._runtime_variables[key] = str(value)

    def get_runtime_variables_dict(self) -> Dict[str, str]:
        """Return a defensive copy of the runtime-variable dict."""
        return dict(self._runtime_variables)

    def get_all_variables(self) -> Dict[str, str]:
        """Return every resolvable variable (user + runtime + built-ins)."""
        return self._merged_variables()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _merged_variables(self) -> Dict[str, str]:
        """Variables in precedence order: user < runtime < built-ins.

        Built-ins sit on top so the worker's contract (built-ins never
        overridable) is enforced even if a runtime variable slips past
        ``add_runtime_variable``'s guard (e.g. constructed directly).
        """
        merged: Dict[str, str] = {}
        merged.update(self._user_variables)
        merged.update(self._runtime_variables)
        merged.update(self._builtins)
        return merged

    @staticmethod
    def _generate_unique_id(length: int = 5) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(random.choices(chars, k=length))  # nosec B311 — not security-sensitive

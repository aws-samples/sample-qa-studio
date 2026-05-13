"""Pure form-builder for the TUI Run form.

Turns the five payloads returned by the API (usecase metadata,
variables, headers, secrets — plus a handful of runner flags) into an
ordered list of :class:`FieldSpec` entries that the Textual form
screen renders verbatim. Given the form's collected values back, the
module also computes the exact override dicts to hand to the subprocess
runner.

No Textual imports. Unit-testable in isolation; the screen layer is
thin glue that asks this module what to render and what to pass on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

FieldSource = Literal[
    "starting_url", "variable", "header", "secret", "runner_flag"
]


@dataclass(frozen=True)
class FieldSpec:
    """Description of a single input on the Run form.

    Attributes:
        key: Stable identifier used to look up the entered value.
            Keys are prefixed by source so a variable named ``region``
            and the runner-flag ``region`` don't collide.
        label: Human-readable label shown next to the input.
        default: Pre-filled value. For secrets this is always ``""``
            (users explicitly re-enter).
        is_secret: ``True`` ⇒ Textual renders a masked Input widget.
        source: Which slot in the override dicts this field feeds.
    """

    key: str
    label: str
    default: str
    is_secret: bool
    source: FieldSource


@dataclass
class OverridesBundle:
    """Result of diffing form values against defaults.

    The three dict fields feed directly into the subprocess runner's
    argv (variables ⇒ repeated ``--var``) / tempfiles (headers ⇒
    ``--headers-file``, secrets ⇒ ``--secrets-file``).  ``base_url``
    is populated when the user changed the starting URL from its
    default.  ``runner_flags`` carries ``region`` / ``model_id`` /
    ``timeout`` when they were changed.
    """

    variables: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    secrets: Dict[str, str] = field(default_factory=dict)
    base_url: Optional[str] = None
    runner_flags: Dict[str, str] = field(default_factory=dict)


def _key(source: FieldSource, name: str) -> str:
    return f"{source}:{name}"


def build_fields(
    usecase: Dict[str, Any],
    variables: Dict[str, str],
    headers: Dict[str, str],
    secrets: List[Dict[str, Any]],
) -> List[FieldSpec]:
    """Flatten the five payloads into an ordered list.

    Order (matches the Run form's top-to-bottom layout):

    1. ``starting_url`` — always present, default from usecase.
    2. Variables — one per declared variable.
    3. Headers — one per declared header.
    4. Secrets — one masked input per declared secret (default always
       empty — the stored value is used when the field is left blank).
    5. Runner flags — ``region`` / ``model_id`` / ``timeout``.
    """
    fields: List[FieldSpec] = []

    fields.append(
        FieldSpec(
            key=_key("starting_url", "url"),
            label="Starting URL",
            default=str(usecase.get("starting_url") or ""),
            is_secret=False,
            source="starting_url",
        )
    )

    for name in sorted(variables):
        fields.append(
            FieldSpec(
                key=_key("variable", name),
                label=name,
                default=str(variables[name]),
                is_secret=False,
                source="variable",
            )
        )

    for name in sorted(headers):
        fields.append(
            FieldSpec(
                key=_key("header", name),
                label=name,
                default=str(headers[name]),
                is_secret=False,
                source="header",
            )
        )

    # Secrets: render masked; default is empty; user types to override.
    for entry in sorted(secrets, key=lambda s: s.get("key", "")):
        name = str(entry.get("key") or "")
        if not name:
            continue
        fields.append(
            FieldSpec(
                key=_key("secret", name),
                label=name,
                default="",
                is_secret=True,
                source="secret",
            )
        )

    # Runner flags — pre-filled from the usecase defaults.
    fields.append(
        FieldSpec(
            key=_key("runner_flag", "region"),
            label="Region",
            default=str(usecase.get("executing_region") or ""),
            is_secret=False,
            source="runner_flag",
        )
    )
    fields.append(
        FieldSpec(
            key=_key("runner_flag", "model_id"),
            label="Model ID",
            default=str(usecase.get("model_id") or ""),
            is_secret=False,
            source="runner_flag",
        )
    )
    fields.append(
        FieldSpec(
            key=_key("runner_flag", "timeout"),
            label="Timeout (s)",
            default="3600",
            is_secret=False,
            source="runner_flag",
        )
    )

    return fields


def compute_overrides(
    fields: List[FieldSpec],
    entered_values: Dict[str, str],
) -> OverridesBundle:
    """Diff ``entered_values`` against each field's default.

    - **Variables / headers / runner flags:** included when the entered
      value differs from the default (empty entries treated as "no
      override" so users can't clear a field to empty string — that
      limitation is documented in the spec as a known POC gap).
    - **Secrets:** included when the entered value is non-empty. A
      blank secret field means "use the stored value" (passthrough to
      the API resolver).
    - **Starting URL:** if changed, emitted as ``base_url`` — the
      runner's ``--base-url`` flag replaces origin+path via
      ``apply_base_url_override``.

    The function is total — missing entries in ``entered_values`` are
    treated the same as matching the default.
    """
    bundle = OverridesBundle()

    for spec in fields:
        entered = entered_values.get(spec.key, spec.default)

        if spec.source == "secret":
            if entered:
                # pull field name back out of the key
                _, _, name = spec.key.partition(":")
                bundle.secrets[name] = entered
            continue

        # Non-secret fields: only emit when changed and non-empty.
        if entered == spec.default or entered == "":
            continue

        _, _, name = spec.key.partition(":")

        if spec.source == "starting_url":
            bundle.base_url = entered
        elif spec.source == "variable":
            bundle.variables[name] = entered
        elif spec.source == "header":
            bundle.headers[name] = entered
        elif spec.source == "runner_flag":
            bundle.runner_flags[name] = entered

    return bundle

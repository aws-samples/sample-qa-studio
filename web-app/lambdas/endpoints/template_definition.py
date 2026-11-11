"""The template file format (``templateVersion: "1.0"``) as a request model.

Shared by ``import_template_definition`` (``POST /templates/import`` — create)
and ``replace_template_definition`` (``PUT /templates/{id}`` — atomic
replace).  Steps may carry an optional ``id``: the replace endpoint matches
existing template steps on it (so linked use-case steps keep a valid
``template_step_id``); the import endpoint ignores it and always generates
new ids.  Duplicate ids within one file are rejected here.

This module imports pydantic, so handlers must ``import lambda_init`` before
importing it (``lambda_init`` adds ``dependencies/`` to ``sys.path``).
"""
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from repeat_validation import template_step_error
from template_expansion import TEMPLATE_STEP_TYPE


class TemplateFileMetadata(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ''
    category: str = ''
    tags: List[str] = Field(default_factory=list)


class TemplateFileStep(BaseModel):
    """A template step: the same shape as an export-JSON step.

    Only the always-required fields are typed; the per-type optional fields
    are copied through ``step_copy.copy_step_fields`` (``extra='allow'``).
    ``id`` is the template step id (``templates export`` emits it).
    """

    model_config = ConfigDict(extra='allow')

    id: Optional[str] = None
    sort: int = Field(..., gt=0)
    step_type: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1)


class TemplateFileVariable(BaseModel):
    key: str = Field(..., min_length=1)
    value: str = ''


class TemplateDefinitionRequest(BaseModel):
    """The template file format (``templateVersion: "1.0"``)."""

    templateVersion: Literal['1.0']
    template: TemplateFileMetadata
    steps: List[TemplateFileStep] = Field(..., min_length=1)
    variables: List[TemplateFileVariable] = Field(default_factory=list)

    @model_validator(mode='after')
    def reject_duplicate_step_ids(self) -> 'TemplateDefinitionRequest':
        seen = set()
        for step in self.steps:
            if step.id is None:
                continue
            if step.id in seen:
                raise ValueError(f'steps: duplicate step id {step.id}')
            seen.add(step.id)
        return self


def validation_message(error: ValidationError) -> str:
    """``loc: msg; loc: msg`` — one line for the 400 body."""
    parts = []
    for err in error.errors():
        loc = '.'.join(str(part) for part in err['loc'])
        msg = err['msg']
        # Model-level ValueErrors already name their location in the message.
        if msg.startswith('Value error, '):
            msg = msg[len('Value error, '):]
        parts.append(f'{loc}: {msg}' if loc else msg)
    return '; '.join(parts)


def step_rule_error(steps: List[TemplateFileStep]) -> Optional[str]:
    """Templates hold plain steps only: no repeat blocks, no dataset references (placeholders are rejected earlier)."""
    for step in steps:
        rule_error = template_step_error(step.model_dump())
        if rule_error:
            return rule_error
    return None


def placeholder_in_steps(raw_steps: Any) -> bool:
    """Pre-schema check: a ``step_type: "template"`` step in the raw body.

    Placeholders have no ``instruction``, so this runs before validation or
    the error would be about the missing field instead of the rule.
    """
    return isinstance(raw_steps, list) and any(
        isinstance(s, dict) and s.get('step_type') == TEMPLATE_STEP_TYPE for s in raw_steps
    )

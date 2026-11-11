"""Resolve the templates referenced by ``step_type: "template"`` placeholders.

``tests import`` does not expand placeholders (``POST /import`` does, keeping
template linkage).  It only needs to know, *before* anything is written,
that every referenced template exists and which secrets it brings along,
so missing templates fail validation and template secrets are prompted
together with the file's own secrets.
"""

import logging
from dataclasses import dataclass, field

from qa_studio_cli.api.client import ApiClient
from qa_studio_cli.api.templates import TemplateAPI
from qa_studio_cli.importers.scanner import ScanResult
from qa_studio_cli.models.api import TemplateStepModel
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.models.import_schema import TemplateRefStep

logger = logging.getLogger(__name__)

NOT_FOUND_HINT = "run 'qa-studio templates list' or 'qa-studio templates create'"


@dataclass(frozen=True)
class ResolvedTemplate:
    id: str
    name: str
    secret_keys: list[str] = field(default_factory=list)


def _secret_keys(steps: list[dict]) -> list[str]:
    keys: list[str] = []
    for raw in steps:
        step = TemplateStepModel.model_validate(raw)
        if step.step_type == "secret" and step.secret_key and step.secret_key not in keys:
            keys.append(step.secret_key)
    return keys


def _fetch(api: TemplateAPI, template_id: str) -> ResolvedTemplate:
    metadata = api.get_template(template_id)
    steps = api.list_steps(template_id)
    return ResolvedTemplate(id=template_id, name=str(metadata.get("name", "")), secret_keys=_secret_keys(steps))


def resolve_templates(client: ApiClient, scan_results: list[ScanResult]) -> dict[str, ResolvedTemplate]:
    """Fetch each distinct referenced template once and annotate the scan results.

    Valid results gain ``templates`` (``[{id, name}]``) and
    ``template_secret_keys``.  A result referencing a template that does not
    exist (or cannot be read) is marked invalid with one error per offending
    placeholder.  Files without placeholders cause no API call.
    """
    api = TemplateAPI(client)
    resolved: dict[str, ResolvedTemplate] = {}
    failures: dict[str, str] = {}

    wanted: list[str] = []
    for result in scan_results:
        if result.is_valid and result.payload is not None:
            for template_id in result.payload.template_ids():
                if template_id not in wanted:
                    wanted.append(template_id)

    for template_id in wanted:
        try:
            resolved[template_id] = _fetch(api, template_id)
        except ApiError as e:
            if e.status_code == 404:
                failures[template_id] = f"template {template_id} not found — {NOT_FOUND_HINT}"
            else:
                failures[template_id] = f"template {template_id}: {e}"
            logger.debug("Could not resolve template %s: %s", template_id, e)

    for result in scan_results:
        if not result.is_valid or result.payload is None:
            continue
        errors: list[str] = []
        templates: list[dict[str, str]] = []
        secret_keys: list[str] = []
        for step in result.payload.steps:
            if not isinstance(step, TemplateRefStep):
                continue
            if step.template_id in failures:
                errors.append(f"step {step.sort}: {failures[step.template_id]}")
                continue
            template = resolved[step.template_id]
            entry = {"id": template.id, "name": template.name}
            if entry not in templates:
                templates.append(entry)
            secret_keys.extend(k for k in template.secret_keys if k not in secret_keys)
        if errors:
            result.is_valid = False
            result.errors.extend(errors)
            continue
        result.templates = templates
        result.template_secret_keys = secret_keys
        result.secrets_count = len(result.secret_keys())
    return resolved

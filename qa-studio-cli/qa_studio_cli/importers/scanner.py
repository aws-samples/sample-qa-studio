"""File discovery and JSON schema validation for test case import."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from qa_studio_cli.models.import_schema import ExportPayload

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of scanning and validating a single file."""

    file_path: Path
    file_name: str
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    payload: Optional[ExportPayload] = None
    usecase_name: str = ""
    step_count: int = 0
    secrets_count: int = 0
    #: Filled by ``template_resolver.resolve_templates``: ``[{id, name}]`` of
    #: the templates referenced by placeholder steps, and the secret keys
    #: those templates bring along (not part of ``payload.secrets``).
    templates: list[dict] = field(default_factory=list)
    template_secret_keys: list[str] = field(default_factory=list)

    def secret_keys(self) -> list[str]:
        """Distinct secret keys this file needs: its own ``secrets`` first, then template secrets."""
        keys: list[str] = []
        if self.payload is not None:
            for secret in self.payload.secrets:
                if secret.key not in keys:
                    keys.append(secret.key)
        for key in self.template_secret_keys:
            if key not in keys:
                keys.append(key)
        return keys

    def secret_description(self, key: str) -> str:
        """Description for prompting: the file's own, else the template that needs it."""
        if self.payload is not None:
            for secret in self.payload.secrets:
                if secret.key == key and secret.description:
                    return secret.description
        if key in self.template_secret_keys:
            names = ", ".join(t["name"] for t in self.templates)
            return f"template: {names}" if names else "template secret"
        return ""


def discover_files(path: Path) -> list[Path]:
    """Resolve path to a list of JSON file candidates.

    If path is a file, returns [path].
    If path is a directory, recursively collects all *.json files.
    """
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.json"))
    return []


def validate_file(file_path: Path) -> ScanResult:
    """Read, parse, and validate a single JSON file against the export schema."""
    file_name = file_path.name

    # Read file
    try:
        raw = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return ScanResult(
            file_path=file_path,
            file_name=file_name,
            is_valid=False,
            errors=[f"Cannot read file: {e}"],
        )

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return ScanResult(
            file_path=file_path,
            file_name=file_name,
            is_valid=False,
            errors=[f"Invalid JSON: {e}"],
        )

    # Validate against schema
    try:
        payload = ExportPayload.model_validate(data)
        return ScanResult(
            file_path=file_path,
            file_name=file_name,
            is_valid=True,
            payload=payload,
            usecase_name=payload.usecase.name,
            step_count=len(payload.steps),
            secrets_count=len(payload.secrets),
        )
    except ValidationError as e:
        return ScanResult(
            file_path=file_path,
            file_name=file_name,
            is_valid=False,
            errors=format_validation_errors(e),
        )


def format_validation_errors(error: ValidationError) -> list[str]:
    """``["<dotted.location>: <message>", ...]`` — one line per pydantic error.

    Shared by ``tests import`` (via ``validate_file``) and ``templates create``
    so both render schema problems the same way.
    """
    errors = []
    for err in error.errors():
        loc = ".".join(str(part) for part in err["loc"])
        errors.append(f"{loc}: {err['msg']}")
    return errors


def scan_all(path: Path) -> list[ScanResult]:
    """Discover and validate all JSON files from the given path."""
    files = discover_files(path)
    return [validate_file(f) for f in files]

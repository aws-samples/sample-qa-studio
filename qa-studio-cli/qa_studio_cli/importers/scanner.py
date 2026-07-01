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
        errors = []
        for err in e.errors():
            loc = ".".join(str(part) for part in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return ScanResult(
            file_path=file_path,
            file_name=file_name,
            is_valid=False,
            errors=errors,
        )


def scan_all(path: Path) -> list[ScanResult]:
    """Discover and validate all JSON files from the given path."""
    files = discover_files(path)
    return [validate_file(f) for f in files]

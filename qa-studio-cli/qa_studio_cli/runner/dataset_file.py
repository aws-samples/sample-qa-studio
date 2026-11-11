"""``qa-studio run --dataset-file [LABEL=]PATH`` support.

Turns a CSV into the ``{"columns": [...], "rows": [[...]]}`` dataset shape
accepted by ``POST /usecase/{id}/execute`` (``repeat_datasets``) and by the
local expansion, and resolves which repeat step each file targets.

CSV rules: ``csv.DictReader``, UTF-8, header row required, every cell read
as a string, blank lines skipped, same caps as the server (100 rows,
20 columns, 200 KB — see ``qa_studio_cli.validation``).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from qa_studio_cli.validation import validate_repeat_dataset

Dataset = Dict[str, Any]
DatasetEntry = Tuple[Optional[str], Dataset]


class DatasetFileError(ValueError):
    """A ``--dataset-file`` value cannot be used (file, shape, or label problem)."""


def parse_dataset_file_option(value: str) -> Tuple[Optional[str], str]:
    """Split ``[LABEL=]PATH`` on the *last* ``=`` (labels may contain ``=``)."""
    if "=" not in value:
        return None, value
    label, _, path = value.rpartition("=")
    if not label:
        raise DatasetFileError(f'--dataset-file "{value}": label before "=" must not be empty')
    if not path:
        raise DatasetFileError(f'--dataset-file "{value}": path after "=" must not be empty')
    return label, path


def read_dataset_csv(path: str) -> Dataset:
    """Read ``path`` into ``{"columns", "rows"}``; raises ``DatasetFileError``."""
    file_path = Path(path)
    if not file_path.is_file():
        raise DatasetFileError(f"dataset file not found: {path}")
    try:
        with file_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            columns: Optional[List[str]] = None
            rows: List[List[str]] = []
            for raw in reader:
                if not raw or all(cell.strip() == "" for cell in raw):
                    continue  # blank line
                if columns is None:
                    columns = [cell.strip() for cell in raw]
                    continue
                if len(raw) > len(columns):
                    raise DatasetFileError(
                        f"{path}: row {len(rows) + 1} has more cells ({len(raw)}) than the header ({len(columns)})"
                    )
                rows.append(list(raw) + [""] * (len(columns) - len(raw)))
    except UnicodeDecodeError as exc:
        raise DatasetFileError(f"{path}: file is not valid UTF-8 ({exc})") from exc
    except csv.Error as exc:
        raise DatasetFileError(f"{path}: cannot parse CSV ({exc})") from exc

    if columns is None:
        raise DatasetFileError(f"{path}: CSV is empty — a header row naming the repeat's columns is required")
    errors = validate_repeat_dataset(columns, rows)
    if errors:
        raise DatasetFileError(f"{path}: " + "; ".join(errors))
    return {"columns": columns, "rows": rows}


def resolve_repeat_datasets(
    entries: List[DatasetEntry],
    steps: List[Dict[str, Any]],
) -> Optional[Dict[str, Dataset]]:
    """Map ``(label|None, dataset)`` entries onto the usecase's repeat steps.

    A missing label is allowed only when the usecase has exactly one repeat.
    Column sets must match the repeat's columns (order-insensitive).  Returns
    ``None`` when ``entries`` is empty.  Raises ``DatasetFileError``.
    """
    if not entries:
        return None
    repeats = [s for s in steps if s.get("step_type") == "repeat"]
    by_label = {s.get("instruction", ""): s for s in repeats}
    resolved: Dict[str, Dataset] = {}
    for label, dataset in entries:
        if label is None:
            if not repeats:
                raise DatasetFileError("--dataset-file given but the usecase has no repeat step")
            if len(repeats) > 1:
                labels = ", ".join(f'"{s.get("instruction", "")}"' for s in repeats)
                raise DatasetFileError(
                    f"the usecase has {len(repeats)} repeat steps ({labels}); "
                    f"specify LABEL=PATH for --dataset-file"
                )
            label = repeats[0].get("instruction", "")
        repeat = by_label.get(label)
        if repeat is None:
            raise DatasetFileError(f'no repeat step with label "{label}" in this usecase')
        if label in resolved:
            raise DatasetFileError(f'--dataset-file targets repeat "{label}" more than once')
        expected = list(repeat.get("repeat_columns") or [])
        if sorted(dataset["columns"]) != sorted(expected):
            raise DatasetFileError(
                f'dataset columns [{", ".join(dataset["columns"])}] do not match the columns of '
                f'repeat "{label}" [{", ".join(expected)}]'
            )
        resolved[label] = dataset
    return resolved

"""Output and error helpers shared by the ``members``, ``teams`` and ``users`` commands.

Only the parts those commands repeated: unwrapping list responses, the
fixed-width table, the "abort unless confirmed" prompt and ApiError → exit 1.
Each command keeps its own options, API call and messages.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Optional, Sequence

import click

from qa_studio_cli.models.errors import ApiError


@contextmanager
def exit_on_api_error() -> Iterator[None]:
    """Print an ApiError in red on stderr and exit 1."""
    try:
        yield
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


def list_items(data: Any, key: str) -> list:
    """The list in a ``{key: [...]}`` response, or the response itself when it is already a list."""
    return data.get(key, data) if isinstance(data, dict) else data


def confirmed(message: str, yes: bool) -> bool:
    """``True`` when ``--yes`` was given or the user confirms; otherwise prints "Aborted."."""
    if yes or click.confirm(message):
        return True
    click.echo("Aborted.")
    return False


@dataclass(frozen=True)
class Column:
    """One table column.

    ``width``: an int pads every cell to exactly that width; ``None`` sizes the
    column to its longest value (at least the header) — unless ``pad`` is
    false, which leaves the column unpadded (last column).
    """

    header: str
    value: Callable[[Any], Any]
    width: Optional[int] = None
    align: str = "<"
    pad: bool = True


def echo_table(rows: Sequence[Any], columns: List[Column]) -> None:
    """Header, a ``─`` rule as wide as the header, then one line per row (two-space gutters)."""
    widths = []
    for col in columns:
        if not col.pad:
            widths.append(None)
        elif col.width is not None:
            widths.append(col.width)
        else:
            widths.append(max(max(len(str(col.value(r))) for r in rows), len(col.header)))

    def line(cells: List[str]) -> str:
        return "  ".join(
            cell if width is None else f"{cell:{col.align}{width}}"
            for cell, col, width in zip(cells, columns, widths)
        )

    header = line([c.header for c in columns])
    click.echo(header)
    click.echo("─" * len(header))
    for row in rows:
        click.echo(line([str(c.value(row)) for c in columns]))

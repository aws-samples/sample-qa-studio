"""Date transform operations.

Five operations layered on top of :mod:`transform.date_parser`:

- ``parse_date``   — value (+ optional format) → canonical UTC ISO 8601 string
- ``format_date``  — canonical ISO value + strftime format → display string
- ``add_duration`` — canonical ISO value + signed amount + unit → ISO string
- ``date_diff``    — two values + unit → signed int (a − b, truncated to int)
- ``to_epoch``     — value (+ unit: seconds|millis) → int

Operations are pure: no clock, no I/O, no non-determinism, in line with the
transform-step contract (``browser-transform-step-types`` R2). Naive
inputs are anchored to UTC by the parser; transforms do not warn on naive
input — that concern lives in the comparison layer (``transform-dates`` R4).
"""

from datetime import timedelta
from typing import ClassVar, Literal, Type

from pydantic import BaseModel

from transform.base import TransformOperation, register_operation
from transform.date_parser import parse_to_utc


_DurationUnit = Literal["seconds", "minutes", "hours", "days", "weeks"]
_EpochUnit = Literal["seconds", "millis"]

# Seconds per unit, used by date_diff to convert a timedelta to a unit count.
_SECONDS_PER_UNIT: dict[str, int] = {
    "seconds": 1,
    "minutes": 60,
    "hours": 60 * 60,
    "days": 60 * 60 * 24,
    "weeks": 60 * 60 * 24 * 7,
}


# ── Arg models ──────────────────────────────────────────────────────────────


class ParseDateArgs(BaseModel):
    value: str
    format: str | None = None


class FormatDateArgs(BaseModel):
    iso_value: str
    format: str


class AddDurationArgs(BaseModel):
    iso_value: str
    amount: int
    unit: _DurationUnit


class DateDiffArgs(BaseModel):
    a: str
    b: str
    unit: _DurationUnit


class ToEpochArgs(BaseModel):
    value: str
    unit: _EpochUnit = "seconds"


# ── Operations ──────────────────────────────────────────────────────────────


class ParseDateOperation(TransformOperation):
    """Parse a date string into canonical UTC ISO 8601."""

    name: ClassVar[str] = "parse_date"
    args_model: ClassVar[Type[BaseModel]] = ParseDateArgs

    def execute(self, args: ParseDateArgs) -> str:
        dt, _was_naive = parse_to_utc(args.value, args.format)
        return dt.isoformat()


class FormatDateOperation(TransformOperation):
    """Render a canonical ISO date in the requested strftime format.

    The input is expected to be already canonical (auto-detect ISO/epoch);
    no explicit input format is accepted here. Use ``parse_date`` first if
    the source isn't canonical.
    """

    name: ClassVar[str] = "format_date"
    args_model: ClassVar[Type[BaseModel]] = FormatDateArgs

    def execute(self, args: FormatDateArgs) -> str:
        dt, _ = parse_to_utc(args.iso_value)
        return dt.strftime(args.format)


class AddDurationOperation(TransformOperation):
    """Add (or subtract, with negative ``amount``) a duration to a date."""

    name: ClassVar[str] = "add_duration"
    args_model: ClassVar[Type[BaseModel]] = AddDurationArgs

    def execute(self, args: AddDurationArgs) -> str:
        dt, _ = parse_to_utc(args.iso_value)
        delta = timedelta(**{args.unit: args.amount})
        return (dt + delta).isoformat()


class DateDiffOperation(TransformOperation):
    """Compute ``a − b`` in the requested unit, truncated toward zero."""

    name: ClassVar[str] = "date_diff"
    args_model: ClassVar[Type[BaseModel]] = DateDiffArgs

    def execute(self, args: DateDiffArgs) -> int:
        dt_a, _ = parse_to_utc(args.a)
        dt_b, _ = parse_to_utc(args.b)
        delta_seconds = (dt_a - dt_b).total_seconds()
        # int() truncates toward zero (e.g. int(-1.7) == -1), which is the
        # spec'd behavior — diffs round toward zero rather than floor.
        return int(delta_seconds / _SECONDS_PER_UNIT[args.unit])


class ToEpochOperation(TransformOperation):
    """Convert a date to a Unix epoch integer (seconds or milliseconds)."""

    name: ClassVar[str] = "to_epoch"
    args_model: ClassVar[Type[BaseModel]] = ToEpochArgs

    def execute(self, args: ToEpochArgs) -> int:
        dt, _ = parse_to_utc(args.value)
        if args.unit == "seconds":
            return int(dt.timestamp())
        return int(dt.timestamp() * 1000)


# ── Register all ────────────────────────────────────────────────────────────

for _op_cls in [
    ParseDateOperation,
    FormatDateOperation,
    AddDurationOperation,
    DateDiffOperation,
    ToEpochOperation,
]:
    register_operation(_op_cls())

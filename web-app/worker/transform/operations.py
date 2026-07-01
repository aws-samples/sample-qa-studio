"""Built-in transform operations: numeric, string, coercion, pattern, format."""

import math
import re
from typing import Any, ClassVar, Type

from pydantic import BaseModel, field_validator

from transform.base import TransformOperation, register_operation


# ── Arg models ──────────────────────────────────────────────────────────────

class SingleNumericArgs(BaseModel):
    value: float

class RoundArgs(BaseModel):
    value: float
    digits: int = 0

class MinMaxArgs(BaseModel):
    values: list[float]

class SingleStringArgs(BaseModel):
    value: str

class ReplaceArgs(BaseModel):
    value: str
    old: str
    new: str

class SubstringArgs(BaseModel):
    value: str
    start: int
    end: int | None = None

class RegexExtractArgs(BaseModel):
    value: str
    pattern: str
    group: int = 0

class FormatArgs(BaseModel):
    template: str
    args: list[str] = []

class ConcatArgs(BaseModel):
    values: list[str]

class CoercionArgs(BaseModel):
    value: str


# ── Numeric operations ──────────────────────────────────────────────────────

class RoundOperation(TransformOperation):
    name: ClassVar[str] = "round"
    args_model: ClassVar[Type[BaseModel]] = RoundArgs
    def execute(self, args: RoundArgs) -> float | int:
        return round(args.value, args.digits)

class FloorOperation(TransformOperation):
    name: ClassVar[str] = "floor"
    args_model: ClassVar[Type[BaseModel]] = SingleNumericArgs
    def execute(self, args: SingleNumericArgs) -> int:
        return math.floor(args.value)

class CeilOperation(TransformOperation):
    name: ClassVar[str] = "ceil"
    args_model: ClassVar[Type[BaseModel]] = SingleNumericArgs
    def execute(self, args: SingleNumericArgs) -> int:
        return math.ceil(args.value)

class AbsOperation(TransformOperation):
    name: ClassVar[str] = "abs"
    args_model: ClassVar[Type[BaseModel]] = SingleNumericArgs
    def execute(self, args: SingleNumericArgs) -> float:
        return abs(args.value)

class MinOperation(TransformOperation):
    name: ClassVar[str] = "min"
    args_model: ClassVar[Type[BaseModel]] = MinMaxArgs
    def execute(self, args: MinMaxArgs) -> float:
        if not args.values:
            raise ValueError("min requires at least one value")
        return min(args.values)

class MaxOperation(TransformOperation):
    name: ClassVar[str] = "max"
    args_model: ClassVar[Type[BaseModel]] = MinMaxArgs
    def execute(self, args: MinMaxArgs) -> float:
        if not args.values:
            raise ValueError("max requires at least one value")
        return max(args.values)


# ── String operations ───────────────────────────────────────────────────────

class ConcatOperation(TransformOperation):
    name: ClassVar[str] = "concat"
    args_model: ClassVar[Type[BaseModel]] = ConcatArgs
    def execute(self, args: ConcatArgs) -> str:
        return "".join(args.values)

class UpperOperation(TransformOperation):
    name: ClassVar[str] = "upper"
    args_model: ClassVar[Type[BaseModel]] = SingleStringArgs
    def execute(self, args: SingleStringArgs) -> str:
        return args.value.upper()

class LowerOperation(TransformOperation):
    name: ClassVar[str] = "lower"
    args_model: ClassVar[Type[BaseModel]] = SingleStringArgs
    def execute(self, args: SingleStringArgs) -> str:
        return args.value.lower()

class TrimOperation(TransformOperation):
    name: ClassVar[str] = "trim"
    args_model: ClassVar[Type[BaseModel]] = SingleStringArgs
    def execute(self, args: SingleStringArgs) -> str:
        return args.value.strip()

class ReplaceOperation(TransformOperation):
    name: ClassVar[str] = "replace"
    args_model: ClassVar[Type[BaseModel]] = ReplaceArgs
    def execute(self, args: ReplaceArgs) -> str:
        return args.value.replace(args.old, args.new)

class SubstringOperation(TransformOperation):
    name: ClassVar[str] = "substring"
    args_model: ClassVar[Type[BaseModel]] = SubstringArgs
    def execute(self, args: SubstringArgs) -> str:
        return args.value[args.start:args.end]

class LengthOperation(TransformOperation):
    name: ClassVar[str] = "length"
    args_model: ClassVar[Type[BaseModel]] = SingleStringArgs
    def execute(self, args: SingleStringArgs) -> int:
        return len(args.value)


# ── Coercion operations ────────────────────────────────────────────────────

class ToNumberOperation(TransformOperation):
    name: ClassVar[str] = "to_number"
    args_model: ClassVar[Type[BaseModel]] = CoercionArgs
    def execute(self, args: CoercionArgs) -> float:
        try:
            return float(args.value)
        except ValueError:
            raise ValueError(f"Cannot convert '{args.value}' to number")

class ToStringOperation(TransformOperation):
    name: ClassVar[str] = "to_string"
    args_model: ClassVar[Type[BaseModel]] = CoercionArgs
    def execute(self, args: CoercionArgs) -> str:
        return str(args.value)

class ToIntOperation(TransformOperation):
    name: ClassVar[str] = "to_int"
    args_model: ClassVar[Type[BaseModel]] = CoercionArgs
    def execute(self, args: CoercionArgs) -> int:
        try:
            return int(float(args.value))
        except ValueError:
            raise ValueError(f"Cannot convert '{args.value}' to int")


# ── Pattern operations ──────────────────────────────────────────────────────

class RegexExtractOperation(TransformOperation):
    name: ClassVar[str] = "regex_extract"
    args_model: ClassVar[Type[BaseModel]] = RegexExtractArgs
    def execute(self, args: RegexExtractArgs) -> str:
        try:
            match = re.search(args.pattern, args.value)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc
        if not match:
            raise ValueError(f"Pattern '{args.pattern}' did not match value")
        try:
            return match.group(args.group)
        except IndexError:
            raise ValueError(f"Group {args.group} not found in match")


# ── Format operation ────────────────────────────────────────────────────────

class FormatOperation(TransformOperation):
    name: ClassVar[str] = "format"
    args_model: ClassVar[Type[BaseModel]] = FormatArgs
    def execute(self, args: FormatArgs) -> str:
        # Reject attribute access ({0.x}) and index access ({0[x]}) in templates
        # to prevent Python format string injection
        import re as _re
        if _re.search(r'\{[^}]*[.\[]', args.template):
            raise ValueError("Format template must not contain attribute or index access (. or [) inside placeholders")
        return args.template.format(*args.args)


# ── Register all ────────────────────────────────────────────────────────────

for _op_cls in [
    RoundOperation, FloorOperation, CeilOperation, AbsOperation,
    MinOperation, MaxOperation,
    ConcatOperation, UpperOperation, LowerOperation, TrimOperation,
    ReplaceOperation, SubstringOperation, LengthOperation,
    ToNumberOperation, ToStringOperation, ToIntOperation,
    RegexExtractOperation, FormatOperation,
]:
    register_operation(_op_cls())

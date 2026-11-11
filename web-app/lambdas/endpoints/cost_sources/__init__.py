"""Cost sources: one module per billed service the collector allocates.

Design: ``.kiro/docs/cost-allocation/design.md`` ("Source interface").  A source
knows how Cost Explorer bills the service (``ce_filter``) and meters the usage
the bill is split by (``usage_by_day``).  The collector (``cost_collector``)
feeds ``DayUsage.seconds_by_usecase`` into ``cost_models.allocate`` as
``usage_by_source[source.name]`` (and ``DayUsage.launches_by_usecase`` as the
compute launch key) and copies the source's run counters into
``CollectorRunReport``.

Two shapes of source exist:

* ``CostSource`` — billed under one Cost Explorer filter, metered from the
  billed service's own API (``nova_act``: ``ListActs``).
* ``ExecutionMeteredSource`` — metered from the system's **own execution
  records** (``compute``: MicroVM timestamps on ``USECASE_EXECUTION#…``).  Its
  bill has more than one allocation key (usage types split by VM seconds vs.
  by launch count — ``classify_usage_type``) and its records live under
  per-use-case partitions, so the collector must tell it which use cases to
  query (``usage_by_day(..., usecase_ids=…)``) — never a table scan.

Sources are additive.  Each returns a ``SourceUsage`` (or a subclass with its
own counters) covering exactly the requested days, so the collector can index
``by_day[day]`` without a default.
"""
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, Literal, Optional, Protocol, Sequence, runtime_checkable

#: Allocation keys a usage type can be split by (``ExecutionMeteredSource.classify_usage_type``).
AllocationKey = Literal['seconds', 'launches']
SECONDS_KEY: AllocationKey = 'seconds'
LAUNCHES_KEY: AllocationKey = 'launches'


@dataclass
class DayUsage:
    """One source's metered usage on one UTC day."""

    #: ``usecase_id → seconds`` — the allocation key for ``cost_models.allocate``.
    #: Keys are already mapped through ``cost_models.workflow_name_to_usecase_id``.
    seconds_by_usecase: Dict[str, float] = field(default_factory=dict)
    #: ``usecase_id → VM launches`` — the compute source's second allocation key
    #: (snapshot usage types); empty for sources without one.
    launches_by_usecase: Dict[str, int] = field(default_factory=dict)
    #: Records that started on this day but whose duration is unknown and
    #: therefore contribute no seconds (Nova Act: acts without ``endedAt``;
    #: compute: executions still running).
    unmeasured: int = 0

    def total_seconds(self) -> float:
        return sum(self.seconds_by_usecase.values())


@dataclass
class SourceUsage:
    """Result of ``CostSource.usage_by_day``: one ``DayUsage`` per requested day."""

    by_day: Dict[dt.date, DayUsage]


class UsageDeadlineExceeded(RuntimeError):
    """A source ran out of the time budget it was handed (``usage_by_day(..., deadline=…)``).

    Raised instead of letting the Lambda time out: the collector reports the
    days as skipped with a clear message, and nothing half-written is left
    behind.  ``source`` names the source, ``done``/``total`` how far it got.
    """

    def __init__(self, source: str, done: int, total: int):
        super().__init__(f'{source}: usage pass exceeded its time budget after {done}/{total} units')
        self.source = source
        self.done = done
        self.total = total


@runtime_checkable
class CostSource(Protocol):
    """What the collector needs from a billed service."""

    #: Source name as stored in ``ServiceCost.service`` (``cost_models.KNOWN_SERVICES``).
    name: str

    @property
    def ce_filter(self) -> Dict[str, Any]:
        """Cost Explorer ``GetCostAndUsage`` ``Filter`` expression selecting this service's bill."""
        ...

    def usage_by_day(self, days: Sequence[dt.date], *, deadline: Optional[float] = None) -> SourceUsage:
        """Metered usage per use case for every day in ``days`` (one pass over the source).

        ``deadline`` is a ``time.monotonic()`` instant; a source that cannot
        finish before it raises ``UsageDeadlineExceeded`` instead of running on.
        """
        ...


@runtime_checkable
class ExecutionMeteredSource(Protocol):
    """A source metered from the system's own execution records (see module docstring).

    Distinguished from a plain ``CostSource`` by ``classify_usage_type``: the
    collector bills it with one ``GroupBy USAGE_TYPE`` call and sums the groups
    per allocation key, and hands ``usage_by_day`` the use case ids the sources
    before it saw.
    """

    name: str

    @property
    def ce_filter(self) -> Dict[str, Any]:
        """Cost Explorer ``Filter`` selecting the whole service the usage types are grouped under."""
        ...

    def classify_usage_type(self, usage_type: str) -> Optional[AllocationKey]:
        """Which key a Cost Explorer ``USAGE_TYPE`` group is split by; ``None`` = not this source's spend."""
        ...

    def usage_by_day(self, days: Sequence[dt.date], *, usecase_ids: Collection[str],
                     deadline: Optional[float] = None) -> SourceUsage:
        """Metered usage for every day in ``days`` over the executions of ``usecase_ids`` (one query per id).

        ``deadline`` as in ``CostSource.usage_by_day``.
        """
        ...


__all__ = [
    'LAUNCHES_KEY',
    'SECONDS_KEY',
    'AllocationKey',
    'CostSource',
    'DayUsage',
    'ExecutionMeteredSource',
    'SourceUsage',
    'UsageDeadlineExceeded',
]

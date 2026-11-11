"""Cost allocation: the ledger / summary models and the two pure functions behind them.

Design: ``.kiro/docs/cost-allocation/design.md``.  One daily collector splits the
real Cost Explorer bill of every source (``nova_act``, ``compute``) over the use
cases that used it, rolls the result up to applications and overall, writes one
``LedgerRow`` per dimension per day into an S3 NDJSON file and recomputes the
dimension's ``CostSummary`` (``USAGE#… / SUMMARY`` item).

This module holds

* the pydantic models every writer and reader serialises through
  (``ServiceCost``, ``Buckets``, ``LedgerRow``, ``CostSummary``,
  ``CollectorRunReport``),
* ``allocate`` — one day's billed amounts + per-use-case usage → rows for every
  dimension,
* ``summarize`` — a dimension's ledger rows → the flat ``window_*`` summary.

Both functions are pure: no AWS calls, no environment, no clock except the
``collected_at`` / ``updated_at`` defaults (pass them explicitly for
reproducible output).

Money is kept at full ``float`` precision in memory and rounded to
``MONEY_DECIMALS`` only when a model is dumped (never round before summing).

Imports pydantic: Lambda entry modules must ``import lambda_init`` first.
"""
import datetime as dt
import json
from decimal import Decimal
from typing import Annotated, Any, Dict, Iterable, List, Literal, Mapping, Optional, Tuple, Union

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from pydantic import BaseModel, Field, PlainSerializer

#: ``change_pct`` within ±this band is reported as ``flat`` (design decision 6).
TREND_FLAT_BAND_PCT = 5.0

#: Summary windows in days; every ``window_{w}d*`` field exists for each entry.
WINDOWS: Tuple[int, ...] = (1, 7, 30)

#: Decimals kept when a money value is serialised (storage); the UI rounds to 2.
MONEY_DECIMALS = 6

#: Known ``ServiceCost.service`` values.  Sources are additive, so the field is
#: a ``str`` rather than an Enum; new sources extend this tuple.
NOVA_ACT_SERVICE = 'nova_act'
COMPUTE_SERVICE = 'compute'
KNOWN_SERVICES: Tuple[str, ...] = (NOVA_ACT_SERVICE, COMPUTE_SERVICE)

SECONDS_PER_HOUR = 3600.0

# ---------------------------------------------------------------------------
# Dimension keys (DynamoDB partition keys of the SUMMARY items)
# ---------------------------------------------------------------------------

OVERALL_DIMENSION_KEY = 'USAGE#OVERALL'
APPLICATION_DIMENSION_PREFIX = 'USAGE#APPLICATION#'
USECASE_DIMENSION_PREFIX = 'USAGE#USECASE#'
SUMMARY_SK = 'SUMMARY'


def application_dimension_key(application_id: str) -> str:
    return f'{APPLICATION_DIMENSION_PREFIX}{application_id}'


def usecase_dimension_key(usecase_id: str) -> str:
    return f'{USECASE_DIMENSION_PREFIX}{usecase_id}'


def workflow_name_to_usecase_id(workflow_name: str) -> str:
    """The use case a Nova Act workflow definition belongs to.

    ``workflow_manager.ensure_workflow`` names the definition after the
    ``usecase_id`` (characters outside ``[a-zA-Z0-9_-]`` become ``-``, cut at
    40).  UUIDv7 ids pass through unchanged, so this is the identity; it exists
    so every caller maps names through one place should the rule ever change.
    """
    return workflow_name


Trend = Literal['up', 'down', 'flat']

#: USD amount: full precision in memory, ``MONEY_DECIMALS`` on output.
Money = Annotated[float, PlainSerializer(lambda value: round(value, MONEY_DECIMALS), return_type=float)]


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
# Ledger row
# ---------------------------------------------------------------------------


class ServiceCost(BaseModel):
    """One source's share of a row: allocated bill, list price and the allocation key."""

    service: str = Field(description='Source name, one of KNOWN_SERVICES ("nova_act", "compute")')
    cost: Money = Field(default=0.0, description='Allocated Cost Explorer bill (USD)')
    list_cost: Money = Field(default=0.0, description='usage_seconds / 3600 × list price per hour (USD)')
    usage_seconds: float = Field(default=0.0, description='Allocation key')
    launches: Optional[int] = Field(default=None, description='compute only: VM launches (snapshot allocation key)')


class Buckets(BaseModel):
    """Bill that no use-case row carries; application and overall rows only (USD)."""

    unassigned: Money = Field(default=0.0, description='Use cases without an application_id (overall row only)')
    unallocated: Money = Field(default=0.0, description='Usage of workflows that are not a use case (any more)')
    unmetered: Money = Field(default=0.0, description='Bill without usage: billed − Σ allocated, ≥ 0')


class LedgerRow(BaseModel):
    """One dimension's cost on one UTC day — one NDJSON line of the dimension's ledger."""

    date: dt.date
    estimated: bool = Field(default=False, description='Cost Explorer "Estimated" flag for that day')
    application_id: Optional[str] = Field(default=None, description='Use case rows: roll-up parent on that date')
    cost: List[ServiceCost] = Field(default_factory=list, description='One entry per source')
    buckets: Optional[Buckets] = Field(default=None, description='Application and overall rows only')
    collected_at: str = Field(description='ISO 8601 UTC time of the last (re-)processing')

    def total(self) -> float:
        """The day's allocated bill: Σ ``cost[].cost``."""
        return sum(entry.cost for entry in self.cost)

    def total_list(self) -> float:
        return sum(entry.list_cost for entry in self.cost)


class UsecaseMeta(BaseModel):
    """What ``allocate`` needs to know about a use case (from ``USECASE#{id}/METADATA``)."""

    application_id: Optional[str] = None
    name: str = ''


# ---------------------------------------------------------------------------
# Summary (USAGE#… / SUMMARY item and the API ``summary`` object)
# ---------------------------------------------------------------------------


class CostSummary(BaseModel):
    """Flat per-dimension summary; the fields follow ``WINDOWS`` (``window_{w}d*``)."""

    as_of: dt.date = Field(description='Newest day included')
    window_1d: Money = 0.0
    window_1d_trend: Optional[Trend] = None
    window_1d_change_pct: Optional[float] = None
    window_1d_list: Money = 0.0
    window_7d: Money = 0.0
    window_7d_trend: Optional[Trend] = None
    window_7d_change_pct: Optional[float] = None
    window_7d_list: Money = 0.0
    window_30d: Money = 0.0
    window_30d_trend: Optional[Trend] = None
    window_30d_change_pct: Optional[float] = None
    window_30d_list: Money = 0.0
    by_source_30d: Dict[str, Money] = Field(default_factory=dict, description='service → USD over the 30d window')
    days_available: int = Field(default=0, description='Ledger rows (≤ as_of) this dimension has')
    estimated_days: int = Field(default=0, description='Rows in the 30d window still "Estimated"')
    updated_at: str = Field(description='ISO 8601 UTC')

    # -- resource-API items (``boto3.resource('dynamodb').Table``) -----------

    def to_item(self, dimension_key: str) -> Dict[str, Any]:
        """The SUMMARY item for ``Table.put_item``: ``pk``/``sk`` plus the fields, numbers as ``Decimal``."""
        return {
            'pk': dimension_key,
            'sk': SUMMARY_SK,
            **json.loads(self.model_dump_json(), parse_float=Decimal),
        }

    @classmethod
    def from_item(cls, item: Mapping[str, Any]) -> 'CostSummary':
        """A ``CostSummary`` from a ``Table.get_item`` item (``Decimal`` numbers, extra keys ignored)."""
        return cls.model_validate({k: v for k, v in item.items() if k in cls.model_fields})

    # -- typed items (low-level client, ``transact_write_items``) -----------

    def to_typed_item(self, dimension_key: str) -> Dict[str, Any]:
        serializer = TypeSerializer()
        return {k: serializer.serialize(v) for k, v in self.to_item(dimension_key).items()}

    @classmethod
    def from_typed_item(cls, item: Mapping[str, Any]) -> 'CostSummary':
        deserializer = TypeDeserializer()
        return cls.from_item({k: deserializer.deserialize(v) for k, v in item.items()})


# ---------------------------------------------------------------------------
# Collector run report
# ---------------------------------------------------------------------------


class SkippedDay(BaseModel):
    day: dt.date
    reason: str = Field(description='e.g. "deadline", "cost_explorer_unavailable"')


class CollectorRunReport(BaseModel):
    """Result of one ``cost_collector`` run; also the ``cost_collector.run`` log line."""

    days: List[dt.date] = Field(default_factory=list, description='Days processed, oldest first')
    billed_usd: float = 0.0
    allocated_usd: float = 0.0
    unallocated_usd: float = 0.0
    unmetered_usd: float = 0.0
    definitions: int = Field(default=0, description='Nova Act workflow definitions seen')
    pages: int = Field(default=0, description='ListActs pages fetched')
    compute_wallclock_fallbacks: int = Field(
        default=0, description='compute: executions metered by completed_at − started_at (no VM timestamps)')
    compute_running_executions: int = Field(
        default=0, description='compute: launched executions without a terminal timestamp (no seconds attributed)')
    files_written: int = 0
    duration_s: float = 0.0
    skipped_days: List[SkippedDay] = Field(default_factory=list)
    continued_with: List[dt.date] = Field(default_factory=list, description='Days handed to a self-invocation')

    def as_log_record(self) -> Dict[str, Any]:
        """The structured log line (JSON-ready, ``event`` first)."""
        return {'event': 'cost_collector.run', **self.model_dump(mode='json')}


# ---------------------------------------------------------------------------
# allocate
# ---------------------------------------------------------------------------

BilledBySource = Mapping[str, Tuple[float, bool]]
UsageBySource = Mapping[str, Mapping[str, float]]
UsecaseMetaInput = Mapping[str, Union[UsecaseMeta, Mapping[str, Any]]]


def allocate(
    day: dt.date,
    billed_by_source: BilledBySource,
    list_price_by_source: Mapping[str, float],
    usage_by_source: UsageBySource,
    launches_by_usecase: Mapping[str, int],
    usecase_meta: UsecaseMetaInput,
    *,
    launch_billed_by_source: Optional[Mapping[str, float]] = None,
    collected_at: Optional[str] = None,
) -> Dict[str, LedgerRow]:
    """Split one day's bill per source over its use cases and roll up; rows keyed by dimension key.

    Args:
        day: the UTC day being allocated.
        billed_by_source: ``source → (Cost Explorer UnblendedCost in USD, Estimated)``
            — the part of the bill split by **seconds**.  A source missing here is
            treated as billed 0 (not estimated).
        list_price_by_source: ``source → list price per hour`` (missing → 0).
        usage_by_source: ``source → usecase_id → seconds``.  Keys are use case ids
            (sources map workflow names through ``workflow_name_to_usecase_id``);
            ids not in ``usecase_meta`` are allocated to the ``unallocated`` bucket.
        launches_by_usecase: ``usecase_id → VM launches`` — the ``compute``
            source's second allocation key; recorded on the ``compute`` entry only.
        usecase_meta: ``usecase_id → UsecaseMeta`` (or a dict with the same keys)
            for every known use case.  An empty ``application_id`` means unassigned.
        launch_billed_by_source: ``source → USD`` — the part of the bill split by
            **launch count** (MicroVM snapshot usage types).  Only the ``compute``
            source may carry one (``ValueError`` otherwise); default: nothing.
        collected_at: ISO 8601 UTC; defaults to now.

    Returns one row per known use case that appears in any source's usage (or
    has launches), one per application those use cases belong to, and the
    overall row.  Every row lists every source (sorted by name) so files stay
    byte-identical between runs.  Per source,
    ``Σ use-case cost + unallocated + unmetered == billed + launch_billed``:
    ``cost[u] = billed × seconds share + launch_billed × launch share``, and each
    part whose key sums to zero goes to ``unmetered`` whole.  The overall row's
    cost equals the application rows plus ``unassigned``.
    """
    collected_at = collected_at or _utc_now_iso()
    launch_billed_by_source = launch_billed_by_source or {}
    foreign = sorted(set(launch_billed_by_source) - {COMPUTE_SERVICE})
    if foreign:
        raise ValueError(f'launch-keyed bill is a {COMPUTE_SERVICE} key; got it for {foreign}')
    meta = {uid: UsecaseMeta.model_validate(m) for uid, m in usecase_meta.items()}
    sources = sorted(set(billed_by_source) | set(usage_by_source) | set(launch_billed_by_source))
    estimated = any(billed_by_source.get(source, (0.0, False))[1] for source in sources)

    per_usecase: Dict[str, Dict[str, ServiceCost]] = {}  # usecase_id → source → entry
    unallocated = 0.0
    unmetered = 0.0
    for source in sources:
        billed, _ = billed_by_source.get(source, (0.0, False))
        launch_billed = launch_billed_by_source.get(source, 0.0)
        price = list_price_by_source.get(source, 0.0)
        usage = usage_by_source.get(source, {})
        launches = launches_by_usecase if source == COMPUTE_SERVICE else {}
        total_usage = sum(usage.values())
        total_launches = sum(launches.values())
        allocated_seconds = 0.0
        allocated_launches = 0.0
        for uid in sorted(set(usage) | set(launches)):
            seconds = usage.get(uid, 0.0)
            # Share first, then scale: keeps the sum exact for a single use case and avoids
            # billed × seconds underflowing for tiny values.
            seconds_cost = billed * (seconds / total_usage) if total_usage > 0 else 0.0
            launch_cost = launch_billed * (launches.get(uid, 0) / total_launches) if total_launches > 0 else 0.0
            allocated_seconds += seconds_cost
            allocated_launches += launch_cost
            if uid not in meta:
                unallocated += seconds_cost + launch_cost
                continue
            per_usecase.setdefault(uid, {})[source] = ServiceCost(
                service=source,
                cost=seconds_cost + launch_cost,
                list_cost=seconds / SECONDS_PER_HOUR * price,
                usage_seconds=seconds,
                launches=_launches_for(source, uid, launches_by_usecase),
            )
        unmetered += max(0.0, billed - allocated_seconds) + max(0.0, launch_billed - allocated_launches)

    # Every use-case row lists every source, zero entries included.
    for uid, entries in per_usecase.items():
        for source in sources:
            entries.setdefault(source, ServiceCost(service=source,
                                                   launches=_launches_for(source, uid, launches_by_usecase)))

    rows: Dict[str, LedgerRow] = {}
    by_application: Dict[str, List[Dict[str, ServiceCost]]] = {}
    unassigned: List[Dict[str, ServiceCost]] = []
    for uid in sorted(per_usecase):
        entries = per_usecase[uid]
        application_id = meta[uid].application_id or None
        rows[usecase_dimension_key(uid)] = LedgerRow(
            date=day, estimated=estimated, application_id=application_id,
            cost=[entries[source] for source in sources], collected_at=collected_at,
        )
        if application_id:
            by_application.setdefault(application_id, []).append(entries)
        else:
            unassigned.append(entries)

    for application_id in sorted(by_application):
        rows[application_dimension_key(application_id)] = LedgerRow(
            date=day, estimated=estimated, cost=_sum_entries(sources, by_application[application_id]),
            buckets=Buckets(), collected_at=collected_at,
        )

    rows[OVERALL_DIMENSION_KEY] = LedgerRow(
        date=day, estimated=estimated, cost=_sum_entries(sources, per_usecase.values()),
        buckets=Buckets(
            unassigned=sum(entry.cost for entries in unassigned for entry in entries.values()),
            unallocated=unallocated,
            unmetered=unmetered,
        ),
        collected_at=collected_at,
    )
    return rows


def _launches_for(source: str, usecase_id: str, launches_by_usecase: Mapping[str, int]) -> Optional[int]:
    if source != COMPUTE_SERVICE:
        return None
    return int(launches_by_usecase.get(usecase_id, 0))


def _sum_entries(sources: List[str], entries: Iterable[Mapping[str, ServiceCost]]) -> List[ServiceCost]:
    """Roll several use cases' per-source entries up into one list (one entry per source)."""
    entries = list(entries)
    summed: List[ServiceCost] = []
    for source in sources:
        parts = [e[source] for e in entries]
        launches = [p.launches for p in parts if p.launches is not None]
        summed.append(ServiceCost(
            service=source,
            cost=sum(p.cost for p in parts),
            list_cost=sum(p.list_cost for p in parts),
            usage_seconds=sum(p.usage_seconds for p in parts),
            launches=sum(launches) if source == COMPUTE_SERVICE else None,
        ))
    return summed


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


def summarize(rows: Iterable[LedgerRow], as_of: dt.date, *, updated_at: Optional[str] = None) -> CostSummary:
    """Fill the ``window_*`` fields of a dimension's summary from its ledger rows.

    Rows dated after ``as_of`` are ignored; dates missing from ``rows`` count as
    0 cost but not toward ``days_available``.  For each window ``w`` the current
    window is ``as_of − w + 1 … as_of`` and the previous one the ``w`` days
    before it.  ``change_pct`` is null when the previous window is 0; the trend
    is null until ``days_available ≥ 2w`` and ``flat`` inside
    ``±TREND_FLAT_BAND_PCT``.  Raises ``ValueError`` on duplicate dates (the
    ledger guarantees one row per date).
    """
    by_date = _rows_by_date(rows, as_of)
    fields: Dict[str, Any] = {'as_of': as_of, 'days_available': len(by_date)}
    for window in WINDOWS:
        current_rows = _rows_between(by_date, as_of - dt.timedelta(days=window - 1), as_of)
        previous_rows = _rows_between(by_date, as_of - dt.timedelta(days=2 * window - 1),
                                      as_of - dt.timedelta(days=window))
        current = sum(row.total() for row in current_rows)
        previous = sum(row.total() for row in previous_rows)
        change_pct = None if previous == 0 else (current - previous) / previous * 100.0
        fields[f'window_{window}d'] = current
        fields[f'window_{window}d_list'] = sum(row.total_list() for row in current_rows)
        fields[f'window_{window}d_change_pct'] = change_pct
        fields[f'window_{window}d_trend'] = (
            _trend(current, previous, change_pct) if len(by_date) >= 2 * window else None
        )

    longest = max(WINDOWS)
    longest_rows = _rows_between(by_date, as_of - dt.timedelta(days=longest - 1), as_of)
    by_source: Dict[str, float] = {}
    for row in longest_rows:
        for entry in row.cost:
            by_source[entry.service] = by_source.get(entry.service, 0.0) + entry.cost
    fields['by_source_30d'] = by_source
    fields['estimated_days'] = sum(1 for row in longest_rows if row.estimated)
    fields['updated_at'] = updated_at or _utc_now_iso()
    return CostSummary(**fields)


def _rows_by_date(rows: Iterable[LedgerRow], as_of: dt.date) -> Dict[dt.date, LedgerRow]:
    by_date: Dict[dt.date, LedgerRow] = {}
    for row in rows:
        if row.date > as_of:
            continue
        if row.date in by_date:
            raise ValueError(f'duplicate ledger row for {row.date.isoformat()}')
        by_date[row.date] = row
    return by_date


def _rows_between(by_date: Mapping[dt.date, LedgerRow], first: dt.date, last: dt.date) -> List[LedgerRow]:
    return [row for day, row in by_date.items() if first <= day <= last]


def _trend(current: float, previous: float, change_pct: Optional[float]) -> Trend:
    if change_pct is None:  # previous window is 0: direction is the sign of the current window
        return 'up' if current > 0 else 'down' if current < 0 else 'flat'
    if change_pct > TREND_FLAT_BAND_PCT:
        return 'up'
    if change_pct < -TREND_FLAT_BAND_PCT:
        return 'down'
    return 'flat'

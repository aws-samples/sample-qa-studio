"""Compute cost source: Lambda MicroVM seconds and launches per use case per day from execution records.

Design: ``.kiro/docs/cost-allocation/design.md`` (Source interface, Spike
findings); task 12.  MicroVMs cannot be tagged (``RunMicrovm`` has no ``tags``,
only images have ARNs, every execution runs the same image), so the MicroVM
bill is split by usage the system meters itself:

* **VM seconds** — ``microvm_terminated_at − microvm_started_at`` on the
  execution record (``execution_transitions.record_microvm_runtime`` writes
  both from ``GetMicrovm`` at the terminal transition; ``GetMicrovm`` forgets a
  VM after < 74 h, so a daily job cannot read them itself).  Records without
  the pair fall back to wall-clock ``completed_at − started_at`` (``created_at``
  when the execution never reached ``running``); every fallback is counted
  (``ComputeUsage.wallclock_fallbacks`` → ``CollectorRunReport``).  Split the
  **compute usage types** (vCPU-s, GB-s).
* **Launches** — execution records carrying a ``microvm_id``.  Split the
  **snapshot usage types** (snapshot read per launch; storage per image-day and
  write per image build are allocated by launch share as a heuristic — spike).

Bill: Cost Explorer rejects ``MatchOptions: STARTS_WITH``, so the collector
calls ``GetCostAndUsage`` once per day with ``Filter SERVICE = "AWS Lambda"``
and ``GroupBy USAGE_TYPE`` (``cost_billing.billed_cost_by_group``) and asks
``classify_usage_type`` which key each group is split by.  Usage types carry a
region prefix (``EUC1-``, ``EU-``, none in ``us-east-1``) that is stripped
before matching the configured stems (``…-ARM`` variants match by prefix).

Usage: executions live at ``pk = USECASE_EXECUTION#{usecase_id}``,
``sk = EXECUTION#{uuid7}``; wizard sessions are execution records under the
same partition.  UUIDv7 is time-ordered, so one ``Query`` per use case with
``sk BETWEEN`` the day bounds (``uuid7_bounds``) finds the executions
**created** in the window without a scan — the launch day is the UUID's
timestamp.  A record created at 23:59 that ran into the next day is attributed
to its launch day, like Nova Act acts are attributed to ``startedAt``.

**Known limitation — which use cases are queried.**  The table has no index
over executions by day, and a scan is not an option (``.kiro/steering/01_dynamodb``).
The collector therefore hands this source the use case ids the sources before
it saw on the same days (``usage_by_day(..., usecase_ids=…)``): a use case
that ran a MicroVM also ran Nova Act acts the same day, so Nova Act's
``ListActs`` pass discovers it.  The exception is a session that launched a VM
but never issued an act (a wizard session closed before the first step, a
runner that crashed before the first act): its seconds and launch are not
metered and its share of the bill lands in ``unmetered``.  The next
re-processing of the day (lookback) does not recover it either — only a day
index would.

Executions still running at collection time have no terminal timestamp: they
count as a launch (the snapshot read was billed) but contribute no seconds
(``DayUsage.unmeasured``, ``ComputeUsage.running_executions``); their compute
share stays in ``unmetered`` until the lookback re-processes the day.

Errors: every ``ClientError`` from ``Query`` propagates to the collector (a
partial compute allocation would silently understate use cases).  Malformed
timestamps raise ``ValueError``.  Log lines carry counts only — never record
contents.

Env (set by the worker stack on the collector Lambda): ``COMPUTE_COST_ENABLED``
(``"true"`` enables the source; default off), ``COMPUTE_CE_SERVICE``,
``COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES``, ``COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES``
(comma-separated stems).
"""
import datetime as dt
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Collection, Dict, Iterator, Mapping, Optional, Sequence, Tuple

from boto3.dynamodb.conditions import Key

from cost_billing import service_filter
from cost_models import COMPUTE_SERVICE
from cost_sources import LAUNCHES_KEY, SECONDS_KEY, AllocationKey, DayUsage, SourceUsage, UsageDeadlineExceeded

logger = logging.getLogger(__name__)

COMPUTE_ENABLED_ENV = 'COMPUTE_COST_ENABLED'
CE_SERVICE_ENV = 'COMPUTE_CE_SERVICE'
COMPUTE_STEMS_ENV = 'COMPUTE_CE_COMPUTE_USAGE_TYPE_PREFIXES'
SNAPSHOT_STEMS_ENV = 'COMPUTE_CE_SNAPSHOT_USAGE_TYPE_PREFIXES'

#: Cost Explorer ``SERVICE`` value MicroVMs bill under (spike).
DEFAULT_CE_SERVICE = 'AWS Lambda'
#: Region-stripped ``USAGE_TYPE`` stems split by VM seconds / by launch count (spike, 2026-11-05).
DEFAULT_COMPUTE_STEMS: Tuple[str, ...] = ('Lambda-MicroVM-vCPU-Second', 'Lambda-MicroVM-Memory-GB-Second')
DEFAULT_SNAPSHOT_STEMS: Tuple[str, ...] = (
    'Lambda-MicroVM-Snapshot-Read-GB',
    'Lambda-MicroVM-Snapshot-Storage-GB-Hour',
    'Lambda-MicroVM-Snapshot-Write-GB',
)

#: ``EUC1-Lambda-…`` → ``Lambda-…``; only an upper-case region code directly followed by ``Lambda-``.
REGION_PREFIX_RE = re.compile(r'^[A-Z0-9]+-(?=Lambda-)')

EXECUTION_PK_PREFIX = 'USECASE_EXECUTION#'
EXECUTION_SK_PREFIX = 'EXECUTION#'

#: Attributes the metering reads (``status`` is a DynamoDB reserved word).
_PROJECTION = 'sk, #s, microvm_id, created_at, started_at, completed_at, microvm_started_at, microvm_terminated_at'
_PROJECTION_NAMES = {'#s': 'status'}

_UTC = dt.timezone.utc
_UUID7_TIMESTAMP_SHIFT = 80   # 128 − 48 bits of Unix milliseconds


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def compute_source_enabled() -> bool:
    """``COMPUTE_COST_ENABLED`` is the literal ``true`` (case-insensitive); anything else is off."""
    return os.environ.get(COMPUTE_ENABLED_ENV, '').strip().lower() == 'true'


def stems_from_env(name: str, default: Sequence[str]) -> Tuple[str, ...]:
    """Comma-separated usage-type stems from env ``name``; unset or blank → ``default``."""
    raw = os.environ.get(name, '')
    stems = tuple(part.strip() for part in raw.split(',') if part.strip())
    return stems or tuple(default)


# ---------------------------------------------------------------------------
# Usage types
# ---------------------------------------------------------------------------


def strip_region_prefix(usage_type: str) -> str:
    """``EUC1-Lambda-MicroVM-vCPU-Second-ARM`` → ``Lambda-MicroVM-vCPU-Second-ARM`` (us-east-1 has no prefix)."""
    return REGION_PREFIX_RE.sub('', usage_type, count=1)


# ---------------------------------------------------------------------------
# UUIDv7 day bounds
# ---------------------------------------------------------------------------


def _format_uuid(value: int) -> str:
    hex_str = f'{value:032x}'
    return f'{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}'


def _day_start_ms(day: dt.date) -> int:
    return int(dt.datetime.combine(day, dt.time.min, tzinfo=_UTC).timestamp() * 1000)


def uuid7_bounds(day: dt.date) -> Tuple[str, str]:
    """Inclusive ``(low, high)`` UUIDv7 strings enclosing every id generated on the UTC ``day``.

    ``low`` is midnight with all other bits 0; ``high`` is the last millisecond
    of the day with all other bits 1 — so consecutive days tile exactly and the
    pair works in a ``BETWEEN`` key condition.  Fixed-width lower-case hex sorts
    like the integer, which is what DynamoDB compares.
    """
    low = _day_start_ms(day) << _UUID7_TIMESTAMP_SHIFT
    high = (_day_start_ms(day + dt.timedelta(days=1)) << _UUID7_TIMESTAMP_SHIFT) - 1
    return _format_uuid(low), _format_uuid(high)


def uuid7_datetime(value: str) -> dt.datetime:
    """The UTC instant encoded in a UUIDv7 (or an ``EXECUTION#{uuid7}`` sort key)."""
    uuid = value[len(EXECUTION_SK_PREFIX):] if value.startswith(EXECUTION_SK_PREFIX) else value
    ms = int(uuid.replace('-', ''), 16) >> _UUID7_TIMESTAMP_SHIFT
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=_UTC)


# ---------------------------------------------------------------------------
# Seconds per execution record
# ---------------------------------------------------------------------------


def _parse_timestamp(value: str) -> dt.datetime:
    """``YYYY-MM-DDTHH:MM:SSZ`` (``utils.get_current_timestamp`` / ``execution_transitions._rfc3339``)."""
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_UTC)


def _duration(start: str, end: str) -> float:
    return max(0.0, (_parse_timestamp(end) - _parse_timestamp(start)).total_seconds())


def execution_seconds(item: Mapping[str, Any]) -> Tuple[Optional[float], bool]:
    """``(seconds, used_wallclock_fallback)`` for one execution record; ``(None, False)`` while it runs.

    VM timestamps win; without the pair the wall-clock ``completed_at −
    started_at`` (``created_at`` when ``started_at`` is missing) is used and
    flagged.  Clock skew that makes the end precede the start yields 0.
    """
    vm_start, vm_end = item.get('microvm_started_at'), item.get('microvm_terminated_at')
    if vm_start and vm_end:
        return _duration(vm_start, vm_end), False
    start, end = item.get('started_at') or item.get('created_at'), item.get('completed_at')
    if start and end:
        return _duration(start, end), True
    return None, False


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


@dataclass
class ComputeUsage(SourceUsage):
    """``usage_by_day`` result plus the run counters the collector reports."""

    usecases_queried: int = 0        #: distinct use case ids handed in (one Query each, plus pages)
    queries: int = 0                 #: ``Query`` pages fetched
    executions: int = 0              #: VM-launched executions created on a requested day
    executions_without_vm: int = 0   #: records in the window without ``microvm_id`` (no VM ran)
    wallclock_fallbacks: int = 0     #: of ``executions``, metered by ``completed_at − started_at``
    running_executions: int = 0      #: of ``executions``, no terminal timestamp yet (no seconds)


class ComputeSource:
    """``ExecutionMeteredSource`` for Lambda MicroVM compute (see module docstring)."""

    name = COMPUTE_SERVICE

    def __init__(self, table, *, service_name: Optional[str] = None,
                 compute_stems: Optional[Sequence[str]] = None, snapshot_stems: Optional[Sequence[str]] = None):
        """``table``: a boto3 DynamoDB ``Table`` resource (``Query`` on the execution partitions)."""
        self._table = table
        self._service_name = service_name or os.environ.get(CE_SERVICE_ENV) or DEFAULT_CE_SERVICE
        self._compute_stems = tuple(compute_stems) if compute_stems is not None else \
            stems_from_env(COMPUTE_STEMS_ENV, DEFAULT_COMPUTE_STEMS)
        self._snapshot_stems = tuple(snapshot_stems) if snapshot_stems is not None else \
            stems_from_env(SNAPSHOT_STEMS_ENV, DEFAULT_SNAPSHOT_STEMS)
        if not self._compute_stems or not self._snapshot_stems:
            raise ValueError('compute source needs at least one compute stem and one snapshot stem')
        overlap = [(a, b) for a in self._compute_stems for b in self._snapshot_stems
                   if a.startswith(b) or b.startswith(a)]
        if overlap:
            raise ValueError(f'compute and snapshot usage-type stems overlap: {overlap}')

    @property
    def ce_filter(self) -> Dict[str, Any]:
        return service_filter(self._service_name)

    def classify_usage_type(self, usage_type: str) -> Optional[AllocationKey]:
        stem = strip_region_prefix(usage_type)
        if stem.startswith(self._compute_stems):
            return SECONDS_KEY
        if stem.startswith(self._snapshot_stems):
            return LAUNCHES_KEY
        return None

    def usage_by_day(self, days: Sequence[dt.date], *, usecase_ids: Collection[str],
                     deadline: Optional[float] = None) -> ComputeUsage:
        """VM seconds and launches per use case for every day in ``days``; one paged ``Query`` per id.

        ``days`` may be unsorted and non-contiguous: one key range spans
        ``min(days) … max(days)``, records on days inside it that were not
        requested are read but not attributed.  Raises ``ValueError`` on an
        empty ``days`` and ``UsageDeadlineExceeded`` when ``deadline``
        (``time.monotonic()``) passes between two use cases.
        """
        if not days:
            raise ValueError('usage_by_day needs at least one day')
        wanted = set(days)
        low, _ = uuid7_bounds(min(wanted))
        _, high = uuid7_bounds(max(wanted))
        usage = ComputeUsage(by_day={day: DayUsage() for day in wanted})

        ids = sorted(set(usecase_ids))
        for usecase_id in ids:
            if deadline is not None and time.monotonic() >= deadline:
                raise UsageDeadlineExceeded(COMPUTE_SERVICE, usage.usecases_queried, len(ids))
            usage.usecases_queried += 1
            for item in self._executions(usecase_id, low, high, usage):
                day_usage = usage.by_day.get(uuid7_datetime(item['sk']).date())
                if day_usage is None:
                    continue  # inside the key range but not a requested day
                if not item.get('microvm_id'):
                    usage.executions_without_vm += 1
                    continue
                usage.executions += 1
                day_usage.launches_by_usecase[usecase_id] = day_usage.launches_by_usecase.get(usecase_id, 0) + 1
                seconds, fallback = execution_seconds(item)
                if seconds is None:
                    usage.running_executions += 1
                    day_usage.unmeasured += 1
                    continue
                if fallback:
                    usage.wallclock_fallbacks += 1
                day_usage.seconds_by_usecase[usecase_id] = day_usage.seconds_by_usecase.get(usecase_id, 0.0) + seconds

        if usage.wallclock_fallbacks:
            logger.warning('%d of %d MicroVM executions in the window have no VM timestamps; '
                           'metered by wall-clock instead', usage.wallclock_fallbacks, usage.executions)
        logger.info('compute usage collected: %d use cases, %d queries, %d executions '
                    '(%d wall-clock fallbacks, %d still running, %d without a VM), %d days',
                    usage.usecases_queried, usage.queries, usage.executions, usage.wallclock_fallbacks,
                    usage.running_executions, usage.executions_without_vm, len(wanted))
        return usage

    def _executions(self, usecase_id: str, low: str, high: str, usage: ComputeUsage) -> Iterator[Dict[str, Any]]:
        """Every execution record of ``usecase_id`` whose UUIDv7 lies in ``[low, high]``, following pagination."""
        condition = Key('pk').eq(f'{EXECUTION_PK_PREFIX}{usecase_id}') & Key('sk').between(
            f'{EXECUTION_SK_PREFIX}{low}', f'{EXECUTION_SK_PREFIX}{high}')
        kwargs: Dict[str, Any] = {
            'KeyConditionExpression': condition,
            'ProjectionExpression': _PROJECTION,
            'ExpressionAttributeNames': dict(_PROJECTION_NAMES),
        }
        while True:
            response = self._table.query(**kwargs)
            usage.queries += 1
            yield from response.get('Items') or []
            last_key = response.get('LastEvaluatedKey')
            if not isinstance(last_key, dict) or not last_key:
                return
            kwargs['ExclusiveStartKey'] = last_key

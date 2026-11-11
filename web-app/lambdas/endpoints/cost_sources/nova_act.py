"""Nova Act cost source: agent seconds per use case per day from ``ListActs``.

Design: ``.kiro/docs/cost-allocation/design.md`` (Allocation, Spike findings).
Every use case has one Nova Act workflow definition named after its
``usecase_id`` (``workflow_manager.ensure_workflow``); the acts under it are
the billed unit's own record.  ``usage_by_day`` makes **one pass** over all
definitions for the whole requested range:

* ``ListWorkflowDefinitions`` paged with ``nextToken`` (``maxResults`` 100);
* per definition ``ListActs(sortOrder='Descending')`` — sorted by ``startedAt``
  (spike) — paged until the first act that started before ``min(days)``;
  ``ListActs`` has no date filter, so this early stop is what keeps the run
  inside the 15-minute Lambda budget.

An act's usage is ``endedAt − startedAt`` in seconds, attributed to the UTC
day of ``startedAt``.  Acts without ``endedAt`` (``TIMED_OUT`` in the spike)
have no measurable duration; they are counted per day in
``DayUsage.unmeasured`` and once per run in ``NovaActUsage.acts_without_end``.

Errors: ``ThrottlingException`` is retried with exponential backoff (same loop
as ``microvm_launch.launch_microvm``); a ``ResourceNotFoundException`` for one
definition (deleted between the two list calls) skips that definition; every
other error propagates to the collector.  Log lines carry counts and
definition names only — never response payloads.

Budget: ``ListActs`` has no date filter, so the scan for a definition runs
from its newest act back to the oldest requested day — the cost of a pass is
proportional to the **age of the oldest requested day**, not to the number of
days asked for (a one-month backfill from five months ago reads five months
of acts).  Definitions are therefore paged **concurrently** (``workers``
threads, env ``NOVA_ACT_LIST_WORKERS``, default ``DEFAULT_WORKERS``); each
worker owns one definition at a time and returns its partial result, the
results are merged in definition order so the output is deterministic.
Progress is logged every ``PROGRESS_EVERY`` definitions.  With a ``deadline``
(``time.monotonic()`` instant) the pass raises ``UsageDeadlineExceeded`` as
soon as a worker would start a page past it — the collector then reports the
days as skipped instead of letting the Lambda time out silently.

The ``nova-act`` API lives in ``us-east-1`` regardless of the stack region
(``NOVA_ACT_REGION``, mirrored from ``qa_studio_cli.runner.workflow_manager``).
"""
import datetime as dt
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, Optional, Sequence

import boto3
from botocore.exceptions import ClientError

from cost_models import NOVA_ACT_SERVICE, workflow_name_to_usecase_id
from cost_sources import DayUsage, SourceUsage, UsageDeadlineExceeded

logger = logging.getLogger(__name__)

#: The Nova Act API region; the Lambda's own region may differ.
NOVA_ACT_REGION = 'us-east-1'

#: Cost Explorer ``SERVICE`` dimension value Nova Act bills under (spike: the
#: literal ``NovaAct``).  Overridden by env ``NOVA_ACT_CE_SERVICE_NAME``.
DEFAULT_CE_SERVICE_NAME = 'NovaAct'
CE_SERVICE_NAME_ENV = 'NOVA_ACT_CE_SERVICE_NAME'

#: ``maxResults`` maximum of both list calls (101 → ``ValidationException``).
PAGE_SIZE = 100

#: Attempts per list call on ``ThrottlingException`` (waits 1, 2, 4, 8 s).
LIST_ATTEMPTS = 5

#: Definitions paged at the same time (spike: ~0.15 s per page serially, no
#: throttling seen; the retry loop absorbs it if the API pushes back).
DEFAULT_WORKERS = 8
LIST_WORKERS_ENV = 'NOVA_ACT_LIST_WORKERS'

#: One progress log line per this many definitions completed.
PROGRESS_EVERY = 25

_UTC = dt.timezone.utc

#: Indirection so tests can silence the backoff without patching ``time.sleep`` globally.
_sleep = time.sleep


def create_nova_act_client():
    """The ``nova-act`` client in its only region."""
    return boto3.client('nova-act', region_name=NOVA_ACT_REGION)


def list_workers() -> int:
    """``NOVA_ACT_LIST_WORKERS`` from the environment (default ``DEFAULT_WORKERS``); must be ≥ 1."""
    raw = os.environ.get(LIST_WORKERS_ENV)
    if raw is None:
        return DEFAULT_WORKERS
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f'{LIST_WORKERS_ENV} must be an integer ≥ 1, got {raw!r}') from None
    if value < 1:
        raise ValueError(f'{LIST_WORKERS_ENV} must be ≥ 1, got {value}')
    return value


@dataclass
class NovaActUsage(SourceUsage):
    """``usage_by_day`` result plus the run counters the collector reports (budget check)."""

    definitions: int = 0        #: workflow definitions listed (skipped ones included)
    pages: int = 0              #: ``ListActs`` pages fetched (retries excluded)
    acts: int = 0               #: acts that started on a requested day
    acts_without_end: int = 0   #: of those, acts without ``endedAt`` (no seconds attributed)
    skipped_definitions: int = 0  #: definitions whose ``ListActs`` raised ``ResourceNotFoundException``


@dataclass
class _DefinitionActs:
    """What one worker collects for one definition; merged into ``NovaActUsage`` by the caller."""

    seconds_by_day: Dict[dt.date, float] = field(default_factory=dict)
    unmeasured_by_day: Dict[dt.date, int] = field(default_factory=dict)
    pages: int = 0
    acts: int = 0
    acts_without_end: int = 0
    skipped: bool = False


class NovaActSource:
    """``CostSource`` for Nova Act (see module docstring)."""

    name = NOVA_ACT_SERVICE

    def __init__(self, client, *, service_name: Optional[str] = None, workers: Optional[int] = None):
        """``client``: a ``nova-act`` boto3 client (``create_nova_act_client()``); boto3 clients are thread-safe."""
        self._client = client
        self._service_name = service_name or os.environ.get(CE_SERVICE_NAME_ENV, DEFAULT_CE_SERVICE_NAME)
        self.workers = workers if workers is not None else list_workers()
        if self.workers < 1:
            raise ValueError(f'workers must be ≥ 1, got {self.workers}')

    @property
    def ce_filter(self) -> Dict[str, Any]:
        return {'Dimensions': {'Key': 'SERVICE', 'Values': [self._service_name]}}

    def usage_by_day(self, days: Sequence[dt.date], *, deadline: Optional[float] = None) -> NovaActUsage:
        """Agent seconds per use case for every day in ``days``; one pass over all definitions.

        ``days`` may be unsorted and non-contiguous; acts on days inside the
        range that were not requested are read (the descending scan has to pass
        them) but not attributed.  Raises ``ValueError`` on an empty ``days``
        and ``UsageDeadlineExceeded`` when ``deadline`` (``time.monotonic()``)
        passes before every definition is paged.
        """
        if not days:
            raise ValueError('usage_by_day needs at least one day')
        wanted = set(days)
        window_start = dt.datetime.combine(min(wanted), dt.time.min, tzinfo=_UTC)
        usage = NovaActUsage(by_day={day: DayUsage() for day in wanted})

        names = [definition['workflowDefinitionName'] for definition in self._workflow_definitions()]
        usage.definitions = len(names)
        self._check_deadline(deadline, done=0, total=len(names))

        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='nova-act-list') as executor:
            futures = [executor.submit(self._collect_acts, name, window_start, wanted, deadline, len(names))
                       for name in names]
            try:
                for index, (name, future) in enumerate(zip(names, futures), start=1):
                    self._merge(usage, workflow_name_to_usecase_id(name), name, future.result())
                    if index % PROGRESS_EVERY == 0 and index < len(names):
                        logger.info('nova_act progress: %d/%d definitions, %d pages, %d acts in window',
                                    index, len(names), usage.pages, usage.acts)
            except BaseException:
                # Deadline or a real error: never start another page; in-flight pages finish.
                executor.shutdown(wait=True, cancel_futures=True)
                raise

        if usage.acts_without_end:
            logger.warning('%d of %d Nova Act acts in the window have no endedAt; their time is not attributed',
                           usage.acts_without_end, usage.acts)
        logger.info('nova_act usage collected: %d definitions (%d skipped), %d pages, %d acts in window, %d days, '
                    '%d workers', usage.definitions, usage.skipped_definitions, usage.pages, usage.acts,
                    len(wanted), self.workers)
        return usage

    # -- paging -----------------------------------------------------------

    def _workflow_definitions(self) -> Iterator[dict]:
        for page in self._pages(self._client.list_workflow_definitions):
            yield from page.get('workflowDefinitionSummaries', [])

    def _collect_acts(self, name: str, window_start: dt.datetime, wanted: set, deadline: Optional[float],
                      total: int) -> _DefinitionActs:
        """One definition's acts in the window (worker thread); stops at the first act older than the window."""
        result = _DefinitionActs()
        try:
            for page in self._pages(self._client.list_acts, deadline=deadline, total=total,
                                    workflowDefinitionName=name, sortOrder='Descending'):
                result.pages += 1
                for summary in page.get('actSummaries', []):
                    started_at = _as_utc(summary['startedAt'])
                    if started_at < window_start:
                        return result  # descending by startedAt: nothing older is in the window
                    day = started_at.date()
                    if day not in wanted:
                        continue  # inside the scan but not a requested day (or newer than the range)
                    result.acts += 1
                    ended_at = summary.get('endedAt')
                    if ended_at is None:
                        result.acts_without_end += 1
                        result.unmeasured_by_day[day] = result.unmeasured_by_day.get(day, 0) + 1
                        continue
                    seconds = (_as_utc(ended_at) - started_at).total_seconds()
                    result.seconds_by_day[day] = result.seconds_by_day.get(day, 0.0) + seconds
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise
            result.skipped = True
            logger.warning('ListActs: workflow definition %s not found, skipped', name)
        return result

    @staticmethod
    def _merge(usage: NovaActUsage, usecase_id: str, name: str, result: _DefinitionActs) -> None:
        """Fold one definition's result into ``usage`` (main thread, definition order → deterministic sums)."""
        usage.pages += result.pages
        usage.acts += result.acts
        usage.acts_without_end += result.acts_without_end
        usage.skipped_definitions += int(result.skipped)
        for day, seconds in result.seconds_by_day.items():
            by_usecase = usage.by_day[day].seconds_by_usecase
            by_usecase[usecase_id] = by_usecase.get(usecase_id, 0.0) + seconds
        for day, count in result.unmeasured_by_day.items():
            usage.by_day[day].unmeasured += count

    def _pages(self, operation: Callable[..., dict], *, deadline: Optional[float] = None, total: int = 0,
               **kwargs) -> Iterator[dict]:
        """Follow ``nextToken`` through one list operation, ``PAGE_SIZE`` per page; checks the deadline per page."""
        next_token = None
        while True:
            self._check_deadline(deadline, done=0, total=total)
            params = dict(kwargs, maxResults=PAGE_SIZE)
            if next_token:
                params['nextToken'] = next_token
            page = _call_with_retry(operation, **params)
            yield page
            next_token = page.get('nextToken')
            if not next_token:
                return

    @staticmethod
    def _check_deadline(deadline: Optional[float], *, done: int, total: int) -> None:
        if deadline is not None and time.monotonic() >= deadline:
            raise UsageDeadlineExceeded(NOVA_ACT_SERVICE, done, total)


def _call_with_retry(operation: Callable[..., dict], **kwargs) -> dict:
    """Call a ``nova-act`` list operation, retrying ``ThrottlingException`` with exponential backoff."""
    for attempt in range(LIST_ATTEMPTS):
        try:
            return operation(**kwargs)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException' and attempt < LIST_ATTEMPTS - 1:
                wait = 2 ** attempt
                logger.warning('nova-act %s throttled, retry %d/%d in %ds',
                               getattr(operation, '__name__', 'list'), attempt + 1, LIST_ATTEMPTS, wait)
                _sleep(wait)
            else:
                raise
    raise RuntimeError('unreachable: nova-act retry loop exited without returning or raising')


def _as_utc(value: dt.datetime) -> dt.datetime:
    """botocore returns tz-aware datetimes; a naive one is taken as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_UTC)
    return value.astimezone(_UTC)

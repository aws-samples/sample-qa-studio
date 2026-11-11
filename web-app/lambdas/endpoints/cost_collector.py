"""Daily cost collector: allocates the Cost Explorer bill per use case, application and overall.

Design: ``.kiro/docs/cost-allocation/design.md``.  One scheduled run (EventBridge,
worker stack) processes the last ``LOOKBACK_DAYS`` UTC days; a manual invoke
re-processes or backfills explicit days.  Per run:

1. **Days** — ``event["days"]`` (list of ``YYYY-MM-DD``) or ``event["from"]`` /
   ``event["to"]`` (inclusive range), else ``today-LOOKBACK … today-1``.
   Always oldest first.
2. **Bill** — ``cost_billing.billed_cost`` per day per source ($0.01 a call);
   an ``ExecutionMeteredSource`` (compute) is billed with
   ``billed_cost_by_group`` instead and its ``USAGE_TYPE`` groups are summed
   per allocation key (``classify_usage_type``: seconds / launches).  A day
   Cost Explorer has no data for is skipped (``cost_explorer_unavailable``)
   before any usage is collected.
3. **Usage** — every source makes one pass over all remaining days
   (``CostSource.usage_by_day``; Nova Act pages ``ListActs`` once for the
   whole window).  An ``ExecutionMeteredSource`` is handed the use case ids
   the sources before it saw (its records live under per-use-case partitions;
   a scan is not an option) — see the compute module for the limitation.
4. **Metadata** — ``application_id`` / ``name`` of every use case seen, one
   ``BatchGetItem`` per 100 ids on ``USECASES / USECASE#{id}`` (never a scan).
5. **Allocate** — ``cost_models.allocate`` per day (seconds-keyed and
   launch-keyed bill parts), guarded by the remaining
   Lambda time: a day is not started with less than ``DEADLINE_GUARD_MS`` left.
   Days left over are reported under ``skipped_days`` (``deadline``); a manual
   run hands them to an asynchronous self-invocation (``continued_with``), a
   scheduled run never does (the next schedule covers them).
6. **Write** — one ``cost_ledger.upsert_rows`` per touched dimension carrying
   every processed day (one read-modify-write per file per run), then the
   dimension's ``USAGE#… / SUMMARY`` item from the last ``SUMMARY_TAIL_ROWS``
   rows of the merged file (no second read).  A touched dimension gets a zero
   row for every processed day it had no usage on; an existing ledger that this
   run did not touch but that holds rows for processed days gets zero rows for
   those days — a re-run never leaves a stale number.

The use-case ledger lives under the application the use case has **at
collection time** for every processed day (``cost_ledger.ledger_key``); a
reassignment inside the lookback therefore lands those days in the new file.

Every write is idempotent: identical inputs with the same ``collected_at``
produce byte-identical files and items.  The run ends with one structured
``cost_collector.run`` log line (``CollectorRunReport.as_log_record``), which
is also the Lambda result.  No raw API responses are stored or logged.

Env: ``TABLE_NAME``, ``S3_BUCKET``, ``LOOKBACK_DAYS`` (default 3),
``NOVA_ACT_CE_SERVICE_NAME`` (read by the Nova Act source),
``COMPUTE_COST_ENABLED`` + ``COMPUTE_CE_*`` (read by the compute source),
``AWS_LAMBDA_FUNCTION_NAME`` (self-invocation target; set by the runtime).

Sources are additive: ``_sources()`` lists them and ``_list_prices`` maps each
to its Pricing ``ServiceCode`` (compute has none: MicroVM list prices are per
vCPU-s / GB-s of a VM size the collector does not know, so its ``list_cost``
stays 0).
"""
import lambda_init  # noqa: F401  — must stay the first import: adds dependencies/ (pydantic) to sys.path
import datetime as dt
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import boto3

from cost_billing import NOVA_ACT_PRICING_SERVICE_CODE, billed_cost, billed_cost_by_group, list_price_per_hour
from cost_ledger import (
    APPLICATION_DIMENSION,
    APPLICATION_FILE,
    LEDGER_PREFIX,
    LEDGER_SUFFIX,
    OVERALL_DIMENSION,
    USECASE_DIMENSION,
    get_ledger_bucket,
    get_s3_client,
    ledger_key,
    read,
    upsert_rows,
)
from cost_models import (
    APPLICATION_DIMENSION_PREFIX,
    COMPUTE_SERVICE,
    NOVA_ACT_SERVICE,
    OVERALL_DIMENSION_KEY,
    USECASE_DIMENSION_PREFIX,
    Buckets,
    CollectorRunReport,
    LedgerRow,
    ServiceCost,
    SkippedDay,
    UsecaseMeta,
    allocate,
    application_dimension_key,
    summarize,
    usecase_dimension_key,
)
from cost_sources import (
    LAUNCHES_KEY,
    SECONDS_KEY,
    CostSource,
    ExecutionMeteredSource,
    SourceUsage,
    UsageDeadlineExceeded,
)
from cost_sources.compute import ComputeSource, compute_source_enabled
from cost_sources.nova_act import LIST_WORKERS_ENV, NovaActSource, create_nova_act_client
from utils import get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_LOOKBACK_DAYS = 3
LOOKBACK_DAYS_ENV = 'LOOKBACK_DAYS'

#: Do not start a day with less than this left; the write phase needs the margin.
DEADLINE_GUARD_MS = 60_000

#: Ledger rows the SUMMARY is computed from (30-day window + its 30-day predecessor).
SUMMARY_TAIL_ROWS = 60

#: ``BatchGetItem`` limit (also enforced by ``fake_table.FakeDynamoResource``).
BATCH_GET_KEYS = 100
#: Rounds of re-requesting ``UnprocessedKeys`` before the run fails.
BATCH_GET_ATTEMPTS = 5

REASON_CE_UNAVAILABLE = 'cost_explorer_unavailable'
REASON_DEADLINE = 'deadline'

#: Pricing API ``ServiceCode`` per source name; a source without one has no list price.
PRICING_SERVICE_CODES: Dict[str, str] = {NOVA_ACT_SERVICE: NOVA_ACT_PRICING_SERVICE_CODE}

_UTC = dt.timezone.utc

BilledBySource = Dict[str, Tuple[float, bool]]


@dataclass
class DayBill:
    """One day's bill per source in the two shapes ``cost_models.allocate`` takes."""

    #: ``source → (USD, estimated)`` — split by metered seconds (every source).
    seconds: BilledBySource = field(default_factory=dict)
    #: ``source → USD`` — split by launch count (``ExecutionMeteredSource`` snapshot usage types only).
    launches: Dict[str, float] = field(default_factory=dict)

    def total(self) -> float:
        return sum(usd for usd, _ in self.seconds.values()) + sum(self.launches.values())


# ---------------------------------------------------------------------------
# Injectable seams (patched in tests)
# ---------------------------------------------------------------------------


def _now() -> dt.datetime:
    return dt.datetime.now(_UTC)


def _dynamodb():
    return boto3.resource('dynamodb')


def _s3_client():
    return get_s3_client()


def _lambda_client():
    return boto3.client('lambda')


def _sources(table) -> List[CostSource]:
    """The cost sources of this deployment, in the order they are collected.

    ``table`` is the DynamoDB ``Table`` resource the compute source queries
    executions from.  Compute is appended only when ``COMPUTE_COST_ENABLED`` is
    ``true``; it must come after Nova Act, whose pass discovers the use case ids
    it queries.
    """
    sources: List[CostSource] = [NovaActSource(create_nova_act_client())]
    if compute_source_enabled():
        sources.append(ComputeSource(table))
    return sources


def _list_prices(sources: Sequence[CostSource]) -> Dict[str, float]:
    """``source name → list price per hour`` for every source with a Pricing ``ServiceCode``."""
    return {
        source.name: list_price_per_hour(PRICING_SERVICE_CODES[source.name])
        for source in sources
        if source.name in PRICING_SERVICE_CODES
    }


# ---------------------------------------------------------------------------
# Day resolution
# ---------------------------------------------------------------------------


def lookback_days() -> int:
    """``LOOKBACK_DAYS`` from the environment (default ``DEFAULT_LOOKBACK_DAYS``); must be ≥ 1."""
    raw = os.environ.get(LOOKBACK_DAYS_ENV)
    if raw is None:
        return DEFAULT_LOOKBACK_DAYS
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f'{LOOKBACK_DAYS_ENV} must be an integer ≥ 1, got {raw!r}') from None
    if value < 1:
        raise ValueError(f'{LOOKBACK_DAYS_ENV} must be ≥ 1, got {value}')
    return value


def resolve_days(event: Optional[Mapping[str, Any]], today: dt.date, lookback_days: int) -> Tuple[List[dt.date], bool]:
    """The UTC days to process (oldest first) and whether the event was a manual override.

    ``event["days"]`` or ``event["from"]``/``event["to"]`` make a manual run;
    anything else (``{}``, ``None``, an EventBridge scheduled event) processes
    ``today-lookback_days … today-1``.  Raises ``ValueError`` with a clear
    message on malformed dates, ``to < from``, or days that are not before
    ``today`` (a day is only billed once it is over).
    """
    event = event or {}
    has_days = 'days' in event
    has_range = 'from' in event or 'to' in event
    if has_days and has_range:
        raise ValueError('event must carry either "days" or "from"/"to", not both')
    if has_days:
        days = event['days']
        if not isinstance(days, list):
            raise ValueError(f'"days" must be a list of YYYY-MM-DD strings, got {type(days).__name__}')
        if not days:
            raise ValueError('"days" must contain at least one day')
        resolved = sorted({_parse_day('days[]', value) for value in days})
    elif has_range:
        if 'from' not in event or 'to' not in event:
            raise ValueError('"from" and "to" must both be given for a range')
        first = _parse_day('from', event['from'])
        last = _parse_day('to', event['to'])
        if last < first:
            raise ValueError(f'"to" ({last.isoformat()}) is before "from" ({first.isoformat()})')
        resolved = [first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)]
    else:
        return [today - dt.timedelta(days=offset) for offset in range(lookback_days, 0, -1)], False

    future = [day for day in resolved if day >= today]
    if future:
        raise ValueError(f'days must be before today ({today.isoformat()}): {[d.isoformat() for d in future]}')
    return resolved, True


def _parse_day(field: str, value: Any) -> dt.date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f'{field} must be a YYYY-MM-DD string, got {value!r}')
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{field} must be a YYYY-MM-DD string, got {value!r}') from None


# ---------------------------------------------------------------------------
# Use-case metadata
# ---------------------------------------------------------------------------


def load_usecase_meta(dynamodb, table_name: str, usecase_ids: Iterable[str]) -> Dict[str, UsecaseMeta]:
    """``usecase_id → UsecaseMeta`` for the ids that exist, via ``BatchGetItem`` in chunks of 100.

    Reads ``USECASES / USECASE#{id}`` (the record ``create_usecase`` writes;
    ``permissions_repo.get_usecase_owner`` reads the same one).  Ids without a
    record are absent from the result — ``allocate`` books their usage to the
    ``unallocated`` bucket.  ``UnprocessedKeys`` are re-requested up to
    ``BATCH_GET_ATTEMPTS`` times; leftovers fail the run rather than silently
    becoming "unallocated".
    """
    ids = sorted(set(usecase_ids))
    meta: Dict[str, UsecaseMeta] = {}
    for start in range(0, len(ids), BATCH_GET_KEYS):
        keys = [{'pk': 'USECASES', 'sk': f'USECASE#{uid}'} for uid in ids[start:start + BATCH_GET_KEYS]]
        for attempt in range(1, BATCH_GET_ATTEMPTS + 1):
            response = dynamodb.batch_get_item(RequestItems={table_name: {
                'Keys': keys,
                'ProjectionExpression': 'sk, application_id, #n',
                'ExpressionAttributeNames': {'#n': 'name'},
            }})
            for item in response.get('Responses', {}).get(table_name, []):
                uid = str(item['sk'])[len('USECASE#'):]
                meta[uid] = UsecaseMeta(application_id=item.get('application_id') or None,
                                        name=str(item.get('name') or ''))
            unprocessed = response.get('UnprocessedKeys') or {}
            keys = list(unprocessed.get(table_name, {}).get('Keys') or []) if isinstance(unprocessed, dict) else []
            if not keys:
                break
            logger.warning('BatchGetItem left %d use-case keys unprocessed (attempt %d/%d)',
                           len(keys), attempt, BATCH_GET_ATTEMPTS)
            time.sleep(min(2 ** (attempt - 1), 8) * 0.1)
        else:
            raise RuntimeError(f'BatchGetItem still has {len(keys)} unprocessed use-case keys '
                               f'after {BATCH_GET_ATTEMPTS} attempts')
    return meta


# ---------------------------------------------------------------------------
# Ledger key ↔ dimension key
# ---------------------------------------------------------------------------


def _ledger_key_for(dimension_key: str, row: LedgerRow) -> str:
    """The S3 ledger of the dimension ``allocate`` produced ``row`` for (use case: under its current app)."""
    if dimension_key == OVERALL_DIMENSION_KEY:
        return ledger_key(OVERALL_DIMENSION)
    if dimension_key.startswith(APPLICATION_DIMENSION_PREFIX):
        return ledger_key(APPLICATION_DIMENSION, dimension_key[len(APPLICATION_DIMENSION_PREFIX):])
    if dimension_key.startswith(USECASE_DIMENSION_PREFIX):
        return ledger_key(USECASE_DIMENSION, row.application_id, dimension_key[len(USECASE_DIMENSION_PREFIX):])
    raise ValueError(f'unknown dimension key {dimension_key!r}')


def _dimension_key_of(s3_key: str) -> Optional[str]:
    """Inverse of ``cost_ledger.ledger_key`` for an existing object; ``None`` for a foreign key."""
    if not s3_key.startswith(LEDGER_PREFIX) or not s3_key.endswith(LEDGER_SUFFIX):
        return None
    parts = s3_key[len(LEDGER_PREFIX):-len(LEDGER_SUFFIX)].split('/')
    if parts == [OVERALL_DIMENSION]:
        return OVERALL_DIMENSION_KEY
    if len(parts) == 2 and all(parts):
        folder, name = parts
        return application_dimension_key(folder) if name == APPLICATION_FILE else usecase_dimension_key(name)
    return None


def _existing_ledger_keys(s3, bucket: str) -> List[str]:
    """Every object key under the ledger prefix (paged ``ListObjectsV2``)."""
    keys: List[str] = []
    kwargs: Dict[str, Any] = {'Bucket': bucket, 'Prefix': LEDGER_PREFIX}
    while True:
        response = s3.list_objects_v2(**kwargs)
        keys.extend(obj['Key'] for obj in response.get('Contents') or [])
        token = response.get('NextContinuationToken') if response.get('IsTruncated') else None
        if not isinstance(token, str) or not token:
            return keys
        kwargs['ContinuationToken'] = token


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _zero_row(day: dt.date, template: LedgerRow, source_names: Sequence[str], estimated: bool,
              collected_at: str) -> LedgerRow:
    """A row with no usage for ``day``, shaped like ``template`` (same parent, buckets present or not)."""
    return LedgerRow(
        date=day,
        estimated=estimated,
        application_id=template.application_id,
        cost=[ServiceCost(service=name, launches=0 if name == COMPUTE_SERVICE else None) for name in source_names],
        buckets=Buckets() if template.buckets is not None else None,
        collected_at=collected_at,
    )


def _stale_rows_of_untouched_ledgers(s3, bucket: str, touched_keys: set, estimated_by_day: Mapping[dt.date, bool],
                                     source_names: Sequence[str], collected_at: str) -> Dict[str, Dict[dt.date, LedgerRow]]:
    """Zero rows for every existing ledger this run did not touch but that has rows on processed days.

    Lists the ledger prefix once and reads each untouched file (a second read
    happens inside ``upsert_rows`` for the few that need a write).  Only the
    days the file already holds are zeroed — no rows are invented for a
    dimension that never had any.  Objects that are not ledgers are ignored
    with a warning.
    """
    stale_by_key: Dict[str, Dict[dt.date, LedgerRow]] = {}
    for key in sorted(set(_existing_ledger_keys(s3, bucket)) - touched_keys):
        if _dimension_key_of(key) is None:
            logger.warning('cost_collector: ignoring foreign object under the ledger prefix: %s', key)
            continue
        existing, _ = read(key, s3=s3, bucket=bucket)
        stale = {row.date: row for row in existing if row.date in estimated_by_day}
        if stale:
            stale_by_key[key] = {day: _zero_row(day, row, source_names, estimated_by_day[day], collected_at)
                                 for day, row in stale.items()}
    return stale_by_key


def _billed_for_day(day: dt.date, sources: Sequence[CostSource]) -> Optional[DayBill]:
    """The day's bill per source; ``None`` when Cost Explorer has no data for any source.

    A plain source is one ``billed_cost`` call.  An ``ExecutionMeteredSource``
    is one ``billed_cost_by_group`` call whose ``USAGE_TYPE`` groups are summed
    into the seconds-keyed and the launch-keyed part by ``classify_usage_type``;
    groups it does not claim are other spend under the same ``SERVICE`` and are
    ignored.  Both calls cost $0.01.
    """
    bill = DayBill()
    for source in sources:
        if isinstance(source, ExecutionMeteredSource):
            grouped = billed_cost_by_group(day, source.ce_filter)
            if grouped is None:
                logger.warning('Cost Explorer has no data for %s (%s): day skipped', day.isoformat(), source.name)
                return None
            seconds_usd, launches_usd, estimated = _sum_groups(day, source, grouped)
            bill.seconds[source.name] = (seconds_usd, estimated)
            bill.launches[source.name] = launches_usd
            continue
        result = billed_cost(day, source.ce_filter)
        if result is None:
            logger.warning('Cost Explorer has no data for %s (%s): day skipped', day.isoformat(), source.name)
            return None
        bill.seconds[source.name] = (result.usd, result.estimated)
    return bill


def _sum_groups(day: dt.date, source: ExecutionMeteredSource,
                grouped: Mapping[str, Any]) -> Tuple[float, float, bool]:
    """``(seconds-keyed USD, launch-keyed USD, estimated)`` over the groups ``source`` claims."""
    seconds_usd = launches_usd = 0.0
    estimated = False
    matched = ignored = 0
    for usage_type, line in grouped.items():
        key = source.classify_usage_type(usage_type)
        if key is None:
            ignored += 1
            continue
        if key == SECONDS_KEY:
            seconds_usd += line.usd
        elif key == LAUNCHES_KEY:
            launches_usd += line.usd
        else:
            raise ValueError(f'{source.name}.classify_usage_type({usage_type!r}) returned unknown key {key!r}')
        matched += 1
        estimated = estimated or line.estimated
    logger.info('%s bill for %s: %d usage types claimed, %d ignored', source.name, day.isoformat(), matched, ignored)
    return seconds_usd, launches_usd, estimated


def _continue_with(remaining: Sequence[dt.date]) -> None:
    """Hand the days this run could not start to a fresh asynchronous invocation of this function."""
    function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
    if not function_name:
        raise RuntimeError('AWS_LAMBDA_FUNCTION_NAME is not set: cannot continue the backfill')
    _lambda_client().invoke(
        FunctionName=function_name,
        InvocationType='Event',
        Payload=json.dumps({'days': [day.isoformat() for day in remaining]}),
    )
    logger.info('cost_collector: %d remaining days handed to a new invocation', len(remaining))


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(event: Optional[Dict[str, Any]], context: Any) -> Dict[str, Any]:
    started = time.monotonic()
    now = _now()
    collected_at = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    days, manual = resolve_days(event, now.date(), lookback_days())
    logger.info('cost_collector: %s run over %s', 'manual' if manual else 'scheduled',
                [day.isoformat() for day in days])

    table_name = get_table_name()
    bucket = get_ledger_bucket()
    dynamodb = _dynamodb()
    table = dynamodb.Table(table_name)
    s3 = _s3_client()
    sources = _sources(table)
    source_names = sorted(source.name for source in sources)
    prices = _list_prices(sources)
    report = CollectorRunReport()

    # 1. Bill per day — cheap; a day without Cost Explorer data costs no ListActs work.
    bill_by_day: Dict[dt.date, DayBill] = {}
    for day in days:
        bill = _billed_for_day(day, sources)
        if bill is None:
            report.skipped_days.append(SkippedDay(day=day, reason=REASON_CE_UNAVAILABLE))
        else:
            bill_by_day[day] = bill
    processable = sorted(bill_by_day)

    # 2. Usage — one pass per source over every processable day, each handed the time left before
    #    the guard as a deadline.  An execution-metered source queries the use cases the sources
    #    before it saw (no scan); hence the order of ``_sources``.
    usage_by_source: Dict[str, SourceUsage] = {}
    seen_ids: Set[str] = set()
    for source in sources if processable else []:
        deadline = time.monotonic() + max(0.0, (context.get_remaining_time_in_millis() - DEADLINE_GUARD_MS) / 1000.0)
        try:
            if isinstance(source, ExecutionMeteredSource):
                usage = source.usage_by_day(processable, usecase_ids=sorted(seen_ids), deadline=deadline)
            else:
                usage = source.usage_by_day(processable, deadline=deadline)
        except UsageDeadlineExceeded as e:
            # Nothing was written, so nothing is half-done.  Re-running the same range cannot succeed:
            # the Nova Act scan cost grows with the age of the oldest requested day, not with the
            # number of days, so no self-invocation — the operator must narrow the range.
            logger.warning('cost_collector: %s. The ListActs scan runs from today back to the oldest requested day '
                           '(%s), so a backfill is only as cheap as that day is recent. Ask for a range that ends '
                           'closer to today, or raise %s (currently %d workers).',
                           e, processable[0].isoformat(), LIST_WORKERS_ENV,
                           getattr(source, 'workers', 0))
            report.skipped_days.extend(SkippedDay(day=d, reason=REASON_DEADLINE) for d in processable)
            report.duration_s = round(time.monotonic() - started, 3)
            logger.info(report.as_log_record())
            raise
        usage_by_source[source.name] = usage
        seen_ids |= _usecase_ids_of(usage)
        report.definitions += int(getattr(usage, 'definitions', 0))
        report.pages += int(getattr(usage, 'pages', 0))
        report.compute_wallclock_fallbacks += int(getattr(usage, 'wallclock_fallbacks', 0))
        report.compute_running_executions += int(getattr(usage, 'running_executions', 0))

    # 3. Metadata of every use case seen (seconds or launches).
    meta = load_usecase_meta(dynamodb, table_name, seen_ids) if seen_ids else {}

    # 4. Allocate day by day behind the deadline guard.
    rows_by_key: Dict[str, Dict[dt.date, LedgerRow]] = {}   # S3 key → day → row
    dimension_by_key: Dict[str, str] = {}                     # S3 key → USAGE#… dimension key
    current_key: Dict[str, str] = {}                          # dimension key → its S3 key at collection time
    estimated_by_day: Dict[dt.date, bool] = {}
    for index, day in enumerate(processable):
        if context.get_remaining_time_in_millis() < DEADLINE_GUARD_MS:
            remaining = processable[index:]
            logger.warning('cost_collector: deadline guard, %d days not started', len(remaining))
            report.skipped_days.extend(SkippedDay(day=d, reason=REASON_DEADLINE) for d in remaining)
            if manual:
                _continue_with(remaining)
                report.continued_with = list(remaining)
            break
        bill = bill_by_day[day]
        rows = allocate(
            day, bill.seconds, prices,
            {name: usage.by_day[day].seconds_by_usecase for name, usage in usage_by_source.items()},
            _launches_for_day(day, usage_by_source), meta,
            launch_billed_by_source=bill.launches, collected_at=collected_at,
        )
        for dimension_key, row in rows.items():
            key = _ledger_key_for(dimension_key, row)
            rows_by_key.setdefault(key, {})[day] = row
            dimension_by_key[key] = dimension_key
            current_key[dimension_key] = key
        overall = rows[OVERALL_DIMENSION_KEY]
        estimated_by_day[day] = overall.estimated
        report.days.append(day)
        report.billed_usd += bill.total()
        report.allocated_usd += overall.total()
        report.unallocated_usd += overall.buckets.unallocated
        report.unmetered_usd += overall.buckets.unmetered

    processed = report.days
    if processed:
        # 5. Touched dimensions carry a row for every processed day (zero where they had no usage).
        for by_day in rows_by_key.values():
            template = by_day[min(by_day)]
            for day in processed:
                if day not in by_day:
                    by_day[day] = _zero_row(day, template, source_names, estimated_by_day[day], collected_at)

        # 6. Existing ledgers this run did not touch: zero out their rows for processed days.
        for key, rows in _stale_rows_of_untouched_ledgers(s3, bucket, set(rows_by_key), estimated_by_day,
                                                          source_names, collected_at).items():
            rows_by_key[key] = rows
            dimension_by_key[key] = _dimension_key_of(key)

        # 7. Write each ledger once; the SUMMARY of a dimension follows its current file only
        #    (an untouched dimension — e.g. a deleted use case — is summarised from its first file).
        summarized: set = set()
        for key in sorted(rows_by_key):
            merged = upsert_rows(key, rows_by_key[key].values(), s3=s3, bucket=bucket)
            report.files_written += 1
            dimension_key = dimension_by_key[key]
            if dimension_key in summarized or current_key.get(dimension_key, key) != key:
                continue
            summary = summarize(_as_stored(merged[-SUMMARY_TAIL_ROWS:]), merged[-1].date, updated_at=collected_at)
            table.put_item(Item=summary.to_item(dimension_key))
            summarized.add(dimension_key)

    report.duration_s = round(time.monotonic() - started, 3)
    # A dict, not json.dumps(...): the Lambda runtime's JSON log format (LoggingFormat.JSON in
    # worker-stack.ts) emits a dict message as a JSON object under `message`, which the
    # `{ $.message.event = "cost_collector.run" }` metric filters read. Under the TEXT format
    # the runtime prints str(dict) - still one readable line.
    logger.info(report.as_log_record())
    return report.model_dump(mode='json')


def _as_stored(rows: Iterable[LedgerRow]) -> List[LedgerRow]:
    """Rows as they read back from the ledger (``Money`` rounded on dump), so the SUMMARY is a function of the file."""
    return [LedgerRow.model_validate_json(row.model_dump_json()) for row in rows]


def _usecase_ids_of(usage: SourceUsage) -> Set[str]:
    """Every use case a source metered seconds or launches for, over all its days."""
    return {uid for day_usage in usage.by_day.values()
            for uid in (*day_usage.seconds_by_usecase, *day_usage.launches_by_usecase)}


def _launches_for_day(day: dt.date, usage_by_source: Mapping[str, SourceUsage]) -> Dict[str, int]:
    """``usecase_id → VM launches`` on ``day`` across sources (only the compute source reports any)."""
    launches: Dict[str, int] = {}
    for usage in usage_by_source.values():
        for uid, count in usage.by_day[day].launches_by_usecase.items():
            launches[uid] = launches.get(uid, 0) + int(count)
    return launches

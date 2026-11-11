"""Tests for the ``cost_collector`` Lambda with ``FakeTable`` + ``FakeDynamoResource``, an in-memory
S3 and a fake cost source / billing — no network.

Design: ``.kiro/docs/cost-allocation/design.md``; task 04.
"""
import datetime as dt
import json
import logging
from typing import Dict, List, Optional, Sequence
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import cost_collector
from cost_billing import BilledDay
from cost_ledger import (
    APPLICATION_DIMENSION,
    LEDGER_PREFIX,
    OVERALL_DIMENSION,
    USECASE_DIMENSION,
    ledger_key,
    read,
    upsert_rows,
)
from cost_models import (
    COMPUTE_SERVICE,
    NOVA_ACT_SERVICE,
    OVERALL_DIMENSION_KEY,
    SUMMARY_SK,
    CollectorRunReport,
    CostSummary,
    LedgerRow,
    application_dimension_key,
    summarize,
    usecase_dimension_key,
)
from cost_sources import LAUNCHES_KEY, SECONDS_KEY, DayUsage, UsageDeadlineExceeded
from cost_sources.compute import ComputeUsage
from cost_sources.nova_act import NovaActUsage
from fake_table import FakeDynamoResource, FakeTable

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 5, 6, 2, 11, tzinfo=UTC)
COLLECTED_AT = '2026-11-05T06:02:11Z'
TODAY = NOW.date()
D1 = dt.date(2026, 11, 4)   # today − 1
D2 = dt.date(2026, 11, 3)   # today − 2
D3 = dt.date(2026, 11, 2)   # today − 3
LOOKBACK = [D3, D2, D1]

TABLE = 'test-table'
BUCKET = 'test-bucket'
FUNCTION = 'studio-cost-collector'
LIST_PRICE = 4.75

APP_A = '0192a000-0000-7000-8000-00000000a001'
APP_B = '0192a000-0000-7000-8000-00000000b002'
UC_A = '0192a000-0000-7000-8000-000000000aaa'   # app A
UC_B = '0192a000-0000-7000-8000-000000000bbb'   # app A
UC_C = '0192a000-0000-7000-8000-000000000ccc'   # unassigned
UC_D = '0192a000-0000-7000-8000-000000000ddd'   # app B
GHOST = '0192a000-0000-7000-8000-00000000dead'  # no use-case record

USECASE_RECORDS = [
    {'pk': 'USECASES', 'sk': f'USECASE#{UC_A}', 'name': 'Login', 'application_id': APP_A},
    {'pk': 'USECASES', 'sk': f'USECASE#{UC_B}', 'name': 'Checkout', 'application_id': APP_A},
    {'pk': 'USECASES', 'sk': f'USECASE#{UC_C}', 'name': 'Orphan'},
    {'pk': 'USECASES', 'sk': f'USECASE#{UC_D}', 'name': 'Search', 'application_id': APP_B},
]

#: usecase → seconds per day used by most tests
USAGE = {
    D3: {UC_A: 600.0, UC_C: 200.0, UC_D: 200.0},
    D2: {UC_A: 300.0, UC_B: 300.0, UC_D: 400.0},
    D1: {UC_A: 900.0, UC_B: 100.0, UC_C: 500.0, UC_D: 500.0},
}
BILLED = {
    D3: BilledDay(usd=10.0, estimated=False, usage_quantity=600.0),
    D2: BilledDay(usd=20.0, estimated=False, usage_quantity=700.0),
    D1: BilledDay(usd=40.0, estimated=True, usage_quantity=1200.0),
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _client_error(code: str, operation: str, status: int = 400) -> ClientError:
    return ClientError({'Error': {'Code': code, 'Message': code}, 'ResponseMetadata': {'HTTPStatusCode': status}},
                       operation)


class FakeS3:
    """``key → (bytes, etag)`` honouring ``IfMatch`` / ``IfNoneMatch`` like S3 conditional writes.

    ``race_once[key] = rows`` makes the *next* ``put_object`` on ``key`` lose a
    race: the concurrent writer's rows are stored first (new ETag), then the
    conditional put fails with 412 — the caller must re-read and merge.
    """

    def __init__(self):
        self.objects: Dict[str, tuple] = {}
        self.put_calls: List[dict] = []
        self.get_calls: List[str] = []
        self.list_calls: List[dict] = []
        self.race_once: Dict[str, bytes] = {}
        self._version = 0

    def _next_etag(self) -> str:
        self._version += 1
        return f'"v{self._version}"'

    def get_object(self, Bucket, Key):  # noqa: N803
        assert Bucket == BUCKET
        self.get_calls.append(Key)
        if Key not in self.objects:
            raise _client_error('NoSuchKey', 'GetObject', 404)
        body, etag = self.objects[Key]
        return {'Body': _Body(body), 'ETag': etag}

    def put_object(self, Bucket, Key, Body, ContentType=None, IfMatch=None, IfNoneMatch=None):  # noqa: N803
        assert Bucket == BUCKET
        self.put_calls.append({'Key': Key, 'IfMatch': IfMatch, 'IfNoneMatch': IfNoneMatch})
        if Key in self.race_once:
            self.objects[Key] = (self.race_once.pop(Key), self._next_etag())
        current = self.objects.get(Key)
        if IfNoneMatch == '*' and current is not None:
            raise _client_error('PreconditionFailed', 'PutObject', 412)
        if IfMatch is not None and (current is None or current[1] != IfMatch):
            raise _client_error('PreconditionFailed', 'PutObject', 412)
        etag = self._next_etag()
        self.objects[Key] = (bytes(Body), etag)
        return {'ETag': etag}

    def snapshot(self) -> Dict[str, bytes]:
        return {key: body for key, (body, _) in self.objects.items()}

    #: keys per ``list_objects_v2`` page (small so tests exercise the continuation token)
    page_size = 1000

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):  # noqa: N803
        assert Bucket == BUCKET
        self.list_calls.append({'Prefix': Prefix, 'ContinuationToken': ContinuationToken})
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken) if ContinuationToken else 0
        page = keys[start:start + self.page_size]
        response = {'Contents': [{'Key': k} for k in page], 'IsTruncated': start + self.page_size < len(keys)}
        if response['IsTruncated']:
            response['NextContinuationToken'] = str(start + self.page_size)
        return response


class _Body:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeSource:
    """A ``CostSource`` answering ``usage_by_day`` from a ``day → usecase → seconds`` dict."""

    name = NOVA_ACT_SERVICE
    ce_filter = {'Dimensions': {'Key': 'SERVICE', 'Values': ['NovaAct'], 'MatchOptions': ['EQUALS']}}

    def __init__(self, usage: Dict[dt.date, Dict[str, float]], *, definitions: int = 5, pages: int = 7):
        self.usage = usage
        self.definitions = definitions
        self.pages = pages
        self.calls: List[List[dt.date]] = []
        self.deadlines: List[Optional[float]] = []
        self.raise_deadline: Optional[Exception] = None

    def usage_by_day(self, days: Sequence[dt.date], *, deadline: Optional[float] = None) -> NovaActUsage:
        self.calls.append(list(days))
        self.deadlines.append(deadline)
        if self.raise_deadline is not None:
            raise self.raise_deadline
        return NovaActUsage(
            by_day={day: DayUsage(seconds_by_usecase=dict(self.usage.get(day, {}))) for day in days},
            definitions=self.definitions, pages=self.pages,
            acts=sum(len(v) for v in self.usage.values()),
        )


class FakeBilling:
    """``billed_cost`` replacement: ``day → BilledDay`` (``None`` = Cost Explorer unavailable)."""

    def __init__(self, billed: Dict[dt.date, Optional[BilledDay]], default: Optional[BilledDay] = None):
        self.billed = billed
        self.default = default if default is not None else BilledDay(usd=0.0, estimated=False, usage_quantity=0.0)
        self.calls: List[tuple] = []

    def __call__(self, day: dt.date, ce_filter, **_) -> Optional[BilledDay]:
        self.calls.append((day, ce_filter))
        return self.billed.get(day, self.default)


COMPUTE_FILTER = {'Dimensions': {'Key': 'SERVICE', 'Values': ['AWS Lambda'], 'MatchOptions': ['EQUALS']}}


def _group(usd: float, estimated: bool = False) -> BilledDay:
    return BilledDay(usd=usd, estimated=estimated, usage_quantity=0.0)


#: Cost Explorer ``GroupBy USAGE_TYPE`` groups per day for the compute source (eu-central-1 shape).
COMPUTE_GROUPS = {
    D3: {'EUC1-Lambda-MicroVM-vCPU-Second-ARM': _group(1.0), 'EUC1-Lambda-MicroVM-Memory-GB-Second-ARM': _group(0.5),
         'EUC1-Lambda-MicroVM-Snapshot-Read-GB': _group(0.3), 'EUC1-Lambda-GB-Second-ARM': _group(9.0)},
    D2: {'EUC1-Lambda-MicroVM-vCPU-Second-ARM': _group(2.0), 'EUC1-Lambda-MicroVM-Snapshot-Storage-GB-Hour': _group(0.2),
         'EUC1-Request-ARM': _group(4.0)},
    D1: {'EUC1-Lambda-MicroVM-vCPU-Second-ARM': _group(3.0, True), 'EUC1-Lambda-MicroVM-Snapshot-Read-GB': _group(0.6, True),
         'EUC1-Lambda-GB-Second-ARM': _group(7.0, True)},
}


class FakeGroupedBilling:
    """``billed_cost_by_group`` replacement: ``day → {usage_type → BilledDay}`` (``None`` = unavailable)."""

    def __init__(self, groups: Dict[dt.date, Optional[Dict[str, BilledDay]]]):
        self.groups = groups
        self.calls: List[tuple] = []

    def __call__(self, day: dt.date, ce_filter, **_) -> Optional[Dict[str, BilledDay]]:
        self.calls.append((day, ce_filter))
        return self.groups.get(day, {})


COMPUTE_USAGE = {
    D3: {UC_A: 100.0},
    D2: {UC_A: 100.0, UC_D: 300.0},
    D1: {UC_B: 50.0, UC_D: 150.0},
}
COMPUTE_LAUNCHES = {
    D3: {UC_A: 1},
    D2: {UC_A: 1, UC_D: 3},
    D1: {UC_B: 1, UC_D: 1, UC_C: 1},   # UC_C: launched, still running → launch only
}


class FakeComputeSource:
    """An ``ExecutionMeteredSource``: seconds and launches from dicts, recording the ids it was handed."""

    name = COMPUTE_SERVICE
    ce_filter = COMPUTE_FILTER

    def __init__(self, usage=None, launches=None, *, wallclock_fallbacks: int = 2, running_executions: int = 1):
        self.usage = COMPUTE_USAGE if usage is None else usage
        self.launches = COMPUTE_LAUNCHES if launches is None else launches
        self.wallclock_fallbacks = wallclock_fallbacks
        self.running_executions = running_executions
        self.calls: List[tuple] = []
        self.deadlines: List[Optional[float]] = []

    def classify_usage_type(self, usage_type: str):
        stem = usage_type.split('-', 1)[1] if usage_type[:4].isupper() and '-Lambda-' in usage_type else usage_type
        if stem.startswith(('Lambda-MicroVM-vCPU-Second', 'Lambda-MicroVM-Memory-GB-Second')):
            return SECONDS_KEY
        if stem.startswith('Lambda-MicroVM-Snapshot-'):
            return LAUNCHES_KEY
        return None

    def usage_by_day(self, days: Sequence[dt.date], *, usecase_ids, deadline: Optional[float] = None) -> ComputeUsage:
        self.calls.append((list(days), sorted(usecase_ids)))
        self.deadlines.append(deadline)
        return ComputeUsage(
            by_day={day: DayUsage(seconds_by_usecase={u: s for u, s in self.usage.get(day, {}).items()
                                                      if u in usecase_ids},
                                  launches_by_usecase={u: n for u, n in self.launches.get(day, {}).items()
                                                       if u in usecase_ids})
                    for day in days},
            wallclock_fallbacks=self.wallclock_fallbacks, running_executions=self.running_executions,
        )


class Harness:
    def __init__(self, table: FakeTable, s3: FakeS3, source: FakeSource, billing: FakeBilling, lambda_client,
                 compute: Optional[FakeComputeSource] = None, grouped_billing: Optional[FakeGroupedBilling] = None):
        self.table = table
        self.resource = FakeDynamoResource(table, TABLE)
        self.s3 = s3
        self.source = source
        self.billing = billing
        self.lambda_client = lambda_client
        self.compute = compute
        self.grouped_billing = grouped_billing
        self.sources_calls: List = []


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', TABLE)
    monkeypatch.setenv('S3_BUCKET', BUCKET)
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', FUNCTION)
    monkeypatch.delenv('LOOKBACK_DAYS', raising=False)
    monkeypatch.delenv('COMPUTE_COST_ENABLED', raising=False)


@pytest.fixture
def harness(monkeypatch):
    """Wires every injectable seam of ``cost_collector`` to in-memory fakes; returns a factory."""
    state: Dict[str, Harness] = {}

    def build(usage=None, billed=None, records=USECASE_RECORDS, s3=None, table=None, compute=None,
              compute_groups=None, **source_kwargs):
        h = Harness(
            table=table if table is not None else FakeTable(records),
            s3=s3 if s3 is not None else FakeS3(),
            source=FakeSource(USAGE if usage is None else usage, **source_kwargs),
            billing=FakeBilling(BILLED if billed is None else billed),
            lambda_client=MagicMock(),
            compute=compute,
            grouped_billing=FakeGroupedBilling(COMPUTE_GROUPS if compute_groups is None else compute_groups),
        )

        def sources(table):
            h.sources_calls.append(table)
            return [h.source] + ([h.compute] if h.compute is not None else [])

        monkeypatch.setattr(cost_collector, '_sources', sources)
        monkeypatch.setattr(cost_collector, '_list_prices', lambda sources: {s.name: LIST_PRICE for s in sources
                                                                             if s.name == NOVA_ACT_SERVICE})
        monkeypatch.setattr(cost_collector, 'billed_cost', h.billing)
        monkeypatch.setattr(cost_collector, 'billed_cost_by_group', h.grouped_billing)
        monkeypatch.setattr(cost_collector, '_dynamodb', lambda: h.resource)
        monkeypatch.setattr(cost_collector, '_s3_client', lambda: h.s3)
        monkeypatch.setattr(cost_collector, '_lambda_client', lambda: h.lambda_client)
        monkeypatch.setattr(cost_collector, '_now', lambda: NOW)
        state['h'] = h
        return h

    return build


def _context(remaining_ms=300_000):
    context = MagicMock()
    if isinstance(remaining_ms, list):
        context.get_remaining_time_in_millis.side_effect = remaining_ms
    else:
        context.get_remaining_time_in_millis.return_value = remaining_ms
    context.function_name = FUNCTION
    return context


def run(event=None, remaining_ms=300_000) -> CollectorRunReport:
    result = cost_collector.handler(event if event is not None else {}, _context(remaining_ms))
    return CollectorRunReport.model_validate(result)


def rows_of(h: Harness, key: str) -> List[LedgerRow]:
    rows, _ = read(key, s3=h.s3, bucket=BUCKET)
    return rows


def summary_item(h: Harness, dimension_key: str) -> Optional[dict]:
    return h.table.get(dimension_key, SUMMARY_SK)


def stored(summary: CostSummary) -> CostSummary:
    """``summary`` as it reads back from DynamoDB (``Money`` rounded on dump, ``Decimal`` round trip)."""
    return CostSummary.from_item(summary.to_item('x'))


OVERALL_KEY = ledger_key(OVERALL_DIMENSION)
APP_A_KEY = ledger_key(APPLICATION_DIMENSION, APP_A)
APP_B_KEY = ledger_key(APPLICATION_DIMENSION, APP_B)
UC_A_KEY = ledger_key(USECASE_DIMENSION, APP_A, UC_A)
UC_B_KEY = ledger_key(USECASE_DIMENSION, APP_A, UC_B)
UC_C_KEY = ledger_key(USECASE_DIMENSION, None, UC_C)
UC_D_KEY = ledger_key(USECASE_DIMENSION, APP_B, UC_D)
ALL_KEYS = {OVERALL_KEY, APP_A_KEY, APP_B_KEY, UC_A_KEY, UC_B_KEY, UC_C_KEY, UC_D_KEY}


# ---------------------------------------------------------------------------
# Day resolution
# ---------------------------------------------------------------------------


class TestResolveDays:
    def test_scheduled_run_uses_lookback_oldest_first(self):
        assert cost_collector.resolve_days({}, TODAY, lookback_days=3) == (LOOKBACK, False)
        assert cost_collector.resolve_days(None, TODAY, lookback_days=1) == ([D1], False)

    def test_eventbridge_scheduled_event_is_not_manual(self):
        event = {'detail-type': 'Scheduled Event', 'source': 'aws.events', 'detail': {}}
        assert cost_collector.resolve_days(event, TODAY, lookback_days=2) == ([D2, D1], False)

    def test_lookback_from_env(self, monkeypatch):
        monkeypatch.setenv('LOOKBACK_DAYS', '5')
        assert cost_collector.lookback_days() == 5
        monkeypatch.delenv('LOOKBACK_DAYS')
        assert cost_collector.lookback_days() == cost_collector.DEFAULT_LOOKBACK_DAYS == 3

    @pytest.mark.parametrize('value', ['0', '-1', 'three', ''])
    def test_invalid_lookback_env_raises(self, monkeypatch, value):
        monkeypatch.setenv('LOOKBACK_DAYS', value)
        with pytest.raises(ValueError, match='LOOKBACK_DAYS'):
            cost_collector.lookback_days()

    def test_days_list_is_sorted_and_deduplicated(self):
        event = {'days': ['2026-11-04', '2026-11-02', '2026-11-04']}
        assert cost_collector.resolve_days(event, TODAY, lookback_days=3) == ([D3, D1], True)

    def test_from_to_is_an_inclusive_range(self):
        event = {'from': '2026-10-30', 'to': '2026-11-01'}
        days, manual = cost_collector.resolve_days(event, TODAY, lookback_days=3)
        assert days == [dt.date(2026, 10, 30), dt.date(2026, 10, 31), dt.date(2026, 11, 1)]
        assert manual is True

    def test_single_day_range(self):
        assert cost_collector.resolve_days({'from': '2026-11-01', 'to': '2026-11-01'}, TODAY, lookback_days=3) == (
            [dt.date(2026, 11, 1)], True)

    @pytest.mark.parametrize('event, message', [
        ({'days': ['2026-13-01']}, 'YYYY-MM-DD'),
        ({'days': 'not-a-list'}, 'list'),
        ({'days': []}, 'at least one'),
        ({'days': ['2026-11-05']}, 'before today'),
        ({'days': ['2027-01-01']}, 'before today'),
        ({'from': '2026-11-03', 'to': '2026-11-01'}, 'to.*before.*from'),
        ({'from': '2026-11-01'}, 'both'),
        ({'to': '2026-11-01'}, 'both'),
        ({'from': '2026-11-01', 'to': '2026-11-05'}, 'before today'),
        ({'from': 'x', 'to': '2026-11-01'}, 'YYYY-MM-DD'),
        ({'days': ['2026-11-01'], 'from': '2026-11-01', 'to': '2026-11-02'}, 'either'),
    ])
    def test_invalid_manual_events_raise(self, event, message):
        with pytest.raises(ValueError, match=message):
            cost_collector.resolve_days(event, TODAY, lookback_days=3)

    def test_handler_propagates_validation_error(self, harness):
        harness()
        with pytest.raises(ValueError, match='before today'):
            run({'days': ['2026-11-05']})


# ---------------------------------------------------------------------------
# Scheduled run: files, summaries, report
# ---------------------------------------------------------------------------


class TestScheduledRun:
    def test_processes_lookback_days_oldest_first_with_one_source_pass(self, harness):
        h = harness()
        report = run()
        assert report.days == LOOKBACK
        assert h.source.calls == [LOOKBACK]
        assert [day for day, _ in h.billing.calls] == LOOKBACK
        assert all(ce_filter == FakeSource.ce_filter for _, ce_filter in h.billing.calls)
        assert report.skipped_days == [] and report.continued_with == []
        h.lambda_client.invoke.assert_not_called()

    def test_writes_one_file_per_dimension_carrying_every_processed_day(self, harness):
        h = harness()
        report = run()
        assert set(h.s3.objects) == ALL_KEYS
        assert report.files_written == len(ALL_KEYS)
        # one read-modify-write per file, not one per day
        assert sorted(call['Key'] for call in h.s3.put_calls) == sorted(ALL_KEYS)
        for key in ALL_KEYS:
            assert [row.date for row in rows_of(h, key)] == LOOKBACK, key

    def test_allocation_matches_cost_models_allocate(self, harness):
        h = harness()
        run()
        overall = {row.date: row for row in rows_of(h, OVERALL_KEY)}
        app_a = {row.date: row for row in rows_of(h, APP_A_KEY)}
        uc_a = {row.date: row for row in rows_of(h, UC_A_KEY)}
        # D1: billed 40 over 2000 s → UC_A 900 s = 18.0, UC_B 100 s = 2.0, UC_C 500 s = 10.0 (unassigned), UC_D 10.0
        assert uc_a[D1].total() == pytest.approx(18.0)
        assert uc_a[D1].application_id == APP_A
        assert uc_a[D1].estimated is True and uc_a[D3].estimated is False
        assert uc_a[D1].cost[0].list_cost == pytest.approx(900.0 / 3600 * LIST_PRICE)
        assert app_a[D1].total() == pytest.approx(20.0)
        assert overall[D1].total() == pytest.approx(40.0)
        assert overall[D1].buckets.unassigned == pytest.approx(10.0)
        assert overall[D1].buckets.unallocated == 0.0 and overall[D1].buckets.unmetered == 0.0
        assert all(row.collected_at == COLLECTED_AT for rows in (overall, app_a, uc_a) for row in rows.values())

    def test_summary_items_match_summarize_over_the_ledger_tail(self, harness):
        h = harness()
        run()
        expected_keys = {OVERALL_DIMENSION_KEY, application_dimension_key(APP_A), application_dimension_key(APP_B),
                         usecase_dimension_key(UC_A), usecase_dimension_key(UC_B), usecase_dimension_key(UC_C),
                         usecase_dimension_key(UC_D)}
        assert {item['pk'] for item in h.table.put_calls} == expected_keys
        assert all(item['sk'] == SUMMARY_SK for item in h.table.put_calls)
        for dimension_key, ledger in ((OVERALL_DIMENSION_KEY, OVERALL_KEY), (usecase_dimension_key(UC_C), UC_C_KEY)):
            rows = rows_of(h, ledger)
            expected = summarize(rows, D1, updated_at=COLLECTED_AT)
            assert CostSummary.from_item(summary_item(h, dimension_key)) == stored(expected)
        overall = CostSummary.from_item(summary_item(h, OVERALL_DIMENSION_KEY))
        assert overall.as_of == D1
        assert overall.window_1d == pytest.approx(40.0)
        assert overall.window_7d == pytest.approx(70.0)
        assert overall.days_available == 3
        assert overall.estimated_days == 1
        assert overall.by_source_30d == {NOVA_ACT_SERVICE: pytest.approx(70.0)}
        assert overall.updated_at == COLLECTED_AT

    def test_summary_uses_the_last_60_rows_and_the_newest_date_as_of(self, harness):
        """A long ledger: as_of is the newest row in the file, the tail is 60 rows (one S3 read per file)."""
        h = harness()
        seeded = [LedgerRow(date=dt.date(2026, 7, 1) + dt.timedelta(days=i), collected_at='old',
                            cost=[{'service': NOVA_ACT_SERVICE, 'cost': 1.0}], buckets={})
                  for i in range(70)]  # 2026-07-01 … 2026-09-08, all before the lookback window
        upsert_rows(OVERALL_KEY, seeded, s3=h.s3, bucket=BUCKET)
        h.s3.get_calls.clear()
        run()
        item = CostSummary.from_item(summary_item(h, OVERALL_DIMENSION_KEY))
        assert item.as_of == D1
        assert item.days_available == 60
        assert h.s3.get_calls.count(OVERALL_KEY) == 1

    def test_backfilled_older_day_does_not_move_as_of_backwards(self, harness):
        h = harness()
        run()
        old = dt.date(2026, 10, 1)
        h2 = harness(usage={old: {UC_A: 100.0}}, billed={old: BilledDay(usd=1.0, estimated=False, usage_quantity=1)},
                     s3=h.s3, table=h.table)
        run({'days': [old.isoformat()]})
        assert [row.date for row in rows_of(h2, OVERALL_KEY)] == [old, *LOOKBACK]
        assert CostSummary.from_item(summary_item(h2, OVERALL_DIMENSION_KEY)).as_of == D1

    def test_report_counters(self, harness):
        h = harness(definitions=11, pages=23)
        report = run()
        assert report.billed_usd == pytest.approx(70.0)
        assert report.allocated_usd == pytest.approx(70.0)
        assert report.unallocated_usd == 0.0 and report.unmetered_usd == 0.0
        assert report.definitions == 11 and report.pages == 23
        assert report.files_written == 7
        assert report.duration_s >= 0.0
        assert h.lambda_client.invoke.assert_not_called() is None

    def test_unknown_workflow_is_unallocated_and_gets_no_file(self, harness):
        h = harness(usage={D1: {UC_A: 100.0, GHOST: 300.0}}, billed={D1: BilledDay(usd=8.0, estimated=False,
                                                                                    usage_quantity=400)})
        report = run({'days': [D1.isoformat()]})
        overall = rows_of(h, OVERALL_KEY)[0]
        assert overall.buckets.unallocated == pytest.approx(6.0)
        assert overall.total() == pytest.approx(2.0)
        assert report.unallocated_usd == pytest.approx(6.0)
        assert report.allocated_usd == pytest.approx(2.0)
        assert not any(GHOST in key for key in h.s3.objects)
        assert summary_item(h, usecase_dimension_key(GHOST)) is None

    def test_bill_without_usage_is_unmetered(self, harness):
        h = harness(usage={}, billed={D1: BilledDay(usd=5.0, estimated=True, usage_quantity=0)})
        report = run({'days': [D1.isoformat()]})
        assert set(h.s3.objects) == {OVERALL_KEY}
        overall = rows_of(h, OVERALL_KEY)[0]
        assert overall.buckets.unmetered == pytest.approx(5.0)
        assert overall.estimated is True
        assert report.unmetered_usd == pytest.approx(5.0)
        assert report.billed_usd == pytest.approx(5.0)
        assert report.allocated_usd == 0.0

    def test_run_log_line_is_structured(self, harness, caplog):
        """The run report is logged as a dict (not a pre-serialised string).

        The Lambda runtime's JSON log format emits a dict ``msg`` without args as a
        JSON object under ``message`` (awslambdaric ``JsonFormatter``), which is what
        the ``{ $.message.event = "cost_collector.run" }`` metric filter in
        worker-stack.ts parses. A string ``msg`` would be a quoted string there.
        """
        harness()
        with caplog.at_level(logging.INFO):
            run()
        run_records = [r for r in caplog.records if isinstance(r.msg, dict) and r.msg.get('event') == 'cost_collector.run']
        assert len(run_records) == 1
        assert run_records[0].args == (), 'args would make the runtime fall back to getMessage()'
        assert not any(isinstance(r.msg, str) and r.msg.startswith('{') for r in caplog.records), 'no pre-serialised JSON string'
        line = run_records[0].msg
        assert json.loads(json.dumps(line)) == line  # JSON-serialisable (model_dump(mode='json'))
        assert line['days'] == [d.isoformat() for d in LOOKBACK]
        for key in ('billed_usd', 'allocated_usd', 'unallocated_usd', 'unmetered_usd', 'definitions', 'pages',
                    'files_written', 'duration_s', 'skipped_days', 'continued_with'):
            assert key in line, key
        assert line['billed_usd'] == pytest.approx(70.0)


# ---------------------------------------------------------------------------
# Idempotence / re-runs
# ---------------------------------------------------------------------------


class TestIdempotence:
    def test_two_runs_over_identical_inputs_are_byte_identical(self, harness):
        h = harness()
        run()
        files_1, items_1 = h.s3.snapshot(), {k: dict(v) for k, v in h.table.items.items()}
        run()
        assert h.s3.snapshot() == files_1
        assert {k: dict(v) for k, v in h.table.items.items()} == items_1
        assert len(h.s3.put_calls) == 2 * len(ALL_KEYS)  # the second run still writes (conditional put)

    def test_rerun_replaces_rows_by_date_without_duplicating(self, harness):
        h = harness()
        run()
        h2 = harness(billed={**BILLED, D1: BilledDay(usd=80.0, estimated=False, usage_quantity=1200)},
                     s3=h.s3, table=h.table)
        run()
        rows = rows_of(h2, OVERALL_KEY)
        assert [row.date for row in rows] == LOOKBACK
        assert rows[-1].total() == pytest.approx(80.0) and rows[-1].estimated is False

    def test_vanished_dimension_gets_a_zero_row_for_the_processed_day(self, harness):
        """UC_B had usage on D2 last run; this run it has usage on D1 only → D2 row becomes zero, not stale."""
        h = harness()
        run()
        assert rows_of(h, UC_B_KEY)[1].total() > 0
        h2 = harness(usage={D3: USAGE[D3], D2: {UC_A: 600.0, UC_D: 400.0}, D1: USAGE[D1]}, s3=h.s3, table=h.table)
        run()
        rows = {row.date: row for row in rows_of(h2, UC_B_KEY)}
        assert [*rows] == LOOKBACK
        zero = rows[D2]
        assert zero.total() == 0.0 and zero.total_list() == 0.0
        assert [entry.service for entry in zero.cost] == [NOVA_ACT_SERVICE]
        assert zero.cost[0].usage_seconds == 0.0
        assert zero.application_id == APP_A
        assert zero.estimated is False
        assert zero.collected_at == COLLECTED_AT
        app_rows = {row.date: row for row in rows_of(h2, APP_A_KEY)}
        assert app_rows[D2].total() == pytest.approx(20.0 * 600.0 / 1000.0)
        # the summary follows the zero row
        summary = CostSummary.from_item(summary_item(h2, usecase_dimension_key(UC_B)))
        assert summary.window_7d == pytest.approx(rows[D1].total() + rows[D3].total())

    def test_touched_dimension_gets_rows_for_every_processed_day(self, harness):
        """A use case seen on one of three days gets zero rows for the other two (zero rows carry buckets for apps)."""
        h = harness(usage={D1: {UC_D: 100.0}}, billed={D1: BilledDay(usd=1.0, estimated=True, usage_quantity=100)})
        run()
        uc_rows = rows_of(h, UC_D_KEY)
        assert [(row.date, row.total()) for row in uc_rows] == [(D3, 0.0), (D2, 0.0), (D1, 1.0)]
        assert [row.estimated for row in uc_rows] == [False, False, True]
        app_rows = rows_of(h, APP_B_KEY)
        assert [row.total() for row in app_rows] == [0.0, 0.0, 1.0]
        assert all(row.buckets is not None for row in app_rows)
        assert all(row.application_id is None for row in app_rows)

    def test_usecase_file_follows_the_application_at_collection_time(self, harness):
        """A reassignment inside the lookback lands every processed day in the new application's file;
        the old file keeps its history but its rows for the processed days are zeroed, and the use case's
        SUMMARY follows the new file only."""
        h = harness()
        run()
        h.table.items[('USECASES', f'USECASE#{UC_B}')]['application_id'] = APP_B
        h2 = harness(s3=h.s3, table=h.table)
        run()
        moved_key = ledger_key(USECASE_DIMENSION, APP_B, UC_B)
        moved = rows_of(h2, moved_key)
        assert [row.date for row in moved] == LOOKBACK
        assert all(row.application_id == APP_B for row in moved)
        old = rows_of(h2, UC_B_KEY)
        assert [row.date for row in old] == LOOKBACK  # old file stays for reprocessing …
        assert all(row.total() == 0.0 and row.application_id == APP_A for row in old)  # … with zeroed days
        app_b = {row.date: row for row in rows_of(h2, APP_B_KEY)}
        assert app_b[D1].total() == pytest.approx(10.0 + 2.0)
        app_a = {row.date: row for row in rows_of(h2, APP_A_KEY)}
        assert app_a[D1].total() == pytest.approx(18.0)
        summary = CostSummary.from_item(summary_item(h2, usecase_dimension_key(UC_B)))
        assert summary == stored(summarize(moved, D1, updated_at=COLLECTED_AT))
        assert summary.window_7d > 0

    def test_untouched_ledger_with_rows_for_processed_days_is_zeroed(self, harness):
        """A deleted use case's definition vanished: its file still has yesterday's D2 number → zero row for D2
        only, its SUMMARY follows; a file with rows outside the processed days is left alone."""
        h = harness()
        stale_key = ledger_key(USECASE_DIMENSION, APP_A, GHOST)
        stale_rows = [
            LedgerRow(date=dt.date(2026, 10, 20), application_id=APP_A, collected_at='old',
                      cost=[{'service': NOVA_ACT_SERVICE, 'cost': 3.0, 'usage_seconds': 30}]),
            LedgerRow(date=D2, application_id=APP_A, collected_at='old',
                      cost=[{'service': NOVA_ACT_SERVICE, 'cost': 7.0, 'usage_seconds': 70}]),
        ]
        upsert_rows(stale_key, stale_rows, s3=h.s3, bucket=BUCKET)
        quiet_key = ledger_key(APPLICATION_DIMENSION, '0192a000-0000-7000-8000-00000000c003')
        upsert_rows(quiet_key, [LedgerRow(date=dt.date(2026, 10, 1), collected_at='old', buckets={},
                                          cost=[{'service': NOVA_ACT_SERVICE, 'cost': 1.0}])],
                    s3=h.s3, bucket=BUCKET)
        h.s3.put_calls.clear()
        report = run()
        rows = {row.date: row for row in rows_of(h, stale_key)}
        assert [*rows] == [dt.date(2026, 10, 20), D2]  # no rows invented for D3 / D1
        assert rows[D2].total() == 0.0 and rows[D2].cost[0].usage_seconds == 0.0
        assert rows[D2].application_id == APP_A and rows[D2].buckets is None
        assert rows[D2].collected_at == COLLECTED_AT and rows[D2].estimated is False
        assert rows[dt.date(2026, 10, 20)].total() == 3.0
        ghost_summary = CostSummary.from_item(summary_item(h, usecase_dimension_key(GHOST)))
        assert ghost_summary == stored(summarize(list(rows.values()), D2, updated_at=COLLECTED_AT))
        assert quiet_key not in {c['Key'] for c in h.s3.put_calls}
        assert summary_item(h, application_dimension_key('0192a000-0000-7000-8000-00000000c003')) is None
        assert report.files_written == len(ALL_KEYS) + 1

    def test_ledger_listing_is_paged_and_ignores_foreign_objects(self, harness, caplog):
        h = harness()
        run()
        h.s3.page_size = 3
        h.s3.objects[f'{LEDGER_PREFIX}notes.txt'] = (b'x', '"foreign"')
        h.s3.list_calls.clear()
        with caplog.at_level(logging.WARNING):
            run()
        assert len(h.s3.list_calls) == 3
        assert all(call['Prefix'] == LEDGER_PREFIX for call in h.s3.list_calls)
        assert any('foreign object' in r.getMessage() for r in caplog.records)
        assert h.s3.objects[f'{LEDGER_PREFIX}notes.txt'] == (b'x', '"foreign"')

    def test_no_listing_when_nothing_was_processed(self, harness):
        h = harness(billed={D3: None, D2: None, D1: None})
        run()
        assert h.s3.list_calls == []


# ---------------------------------------------------------------------------
# Skipped days, deadline and continuation
# ---------------------------------------------------------------------------


class TestSkipsAndDeadline:
    def test_cost_explorer_unavailable_day_is_skipped_and_others_processed(self, harness):
        h = harness(billed={**BILLED, D2: None})
        report = run()
        assert report.days == [D3, D1]
        assert [(s.day, s.reason) for s in report.skipped_days] == [(D2, 'cost_explorer_unavailable')]
        for key in ALL_KEYS:
            assert [row.date for row in rows_of(h, key)] == [D3, D1], key
        assert report.billed_usd == pytest.approx(50.0)
        h.lambda_client.invoke.assert_not_called()

    def test_all_days_unavailable_writes_nothing(self, harness):
        h = harness(billed={D3: None, D2: None, D1: None})
        report = run()
        assert report.days == [] and report.files_written == 0
        assert h.s3.put_calls == [] and h.table.put_calls == []
        assert [s.reason for s in report.skipped_days] == ['cost_explorer_unavailable'] * 3

    def test_deadline_on_manual_range_self_invokes_with_the_remainder(self, harness):
        h = harness()
        remaining = [300_000, 300_000, 300_000, 30_000]  # usage-pass deadline, then D3 ok, D2 ok, D1 under the guard
        report = run({'from': D3.isoformat(), 'to': D1.isoformat()}, remaining_ms=remaining)
        assert report.days == [D3, D2]
        assert [(s.day, s.reason) for s in report.skipped_days] == [(D1, 'deadline')]
        assert report.continued_with == [D1]
        h.lambda_client.invoke.assert_called_once()
        kwargs = h.lambda_client.invoke.call_args.kwargs
        assert kwargs['FunctionName'] == FUNCTION
        assert kwargs['InvocationType'] == 'Event'
        assert json.loads(kwargs['Payload']) == {'days': [D1.isoformat()]}
        for key in ALL_KEYS:
            assert [row.date for row in rows_of(h, key)] == [D3, D2], key

    def test_deadline_on_days_list_self_invokes_with_all_remaining_days(self, harness):
        h = harness()
        report = run({'days': [D1.isoformat(), D3.isoformat(), D2.isoformat()]}, remaining_ms=[300_000, 300_000, 10_000])
        assert report.days == [D3]
        assert report.continued_with == [D2, D1]
        assert json.loads(h.lambda_client.invoke.call_args.kwargs['Payload']) == {'days': [D2.isoformat(),
                                                                                             D1.isoformat()]}

    def test_deadline_on_scheduled_run_only_skips(self, harness):
        h = harness()
        report = run({}, remaining_ms=[300_000, 300_000, 30_000])
        assert report.days == [D3]
        assert [(s.day, s.reason) for s in report.skipped_days] == [(D2, 'deadline'), (D1, 'deadline')]
        assert report.continued_with == []
        h.lambda_client.invoke.assert_not_called()

    def test_deadline_before_the_first_day_processes_nothing(self, harness):
        h = harness()
        report = run({}, remaining_ms=1_000)
        assert report.days == [] and report.files_written == 0
        assert h.s3.put_calls == []
        assert len(report.skipped_days) == 3

    def test_continuation_without_function_name_fails_loudly(self, harness, monkeypatch):
        harness()
        monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME')
        with pytest.raises(RuntimeError, match='AWS_LAMBDA_FUNCTION_NAME'):
            run({'days': [D2.isoformat(), D1.isoformat()]}, remaining_ms=[300_000, 300_000, 10_000])

    def test_sources_receive_a_deadline_derived_from_the_remaining_time(self, harness, monkeypatch):
        h = harness(compute=FakeComputeSource())
        monkeypatch.setattr(cost_collector.time, 'monotonic', lambda: 1_000.0)
        run(remaining_ms=300_000)
        # remaining 300 s minus the 60 s guard = 240 s after "now"
        assert h.source.deadlines == [1_240.0]
        assert h.compute.deadlines == [1_240.0]

    def test_usage_deadline_exceeded_reports_the_days_and_raises(self, harness, caplog):
        h = harness()
        h.source.raise_deadline = UsageDeadlineExceeded(NOVA_ACT_SERVICE, 40, 255)
        with caplog.at_level(logging.INFO):
            with pytest.raises(UsageDeadlineExceeded, match='40/255'):
                run({'from': D3.isoformat(), 'to': D1.isoformat()})
        assert h.s3.put_calls == [] and h.table.put_calls == []
        h.lambda_client.invoke.assert_not_called()   # re-running the same range cannot succeed
        messages = ' '.join(r.getMessage() for r in caplog.records)
        assert 'oldest requested day' in messages and 'NOVA_ACT_LIST_WORKERS' in messages
        run_lines = [r.msg for r in caplog.records if isinstance(r.msg, dict) and r.msg.get('event') == 'cost_collector.run']
        assert len(run_lines) == 1
        assert [(s['day'], s['reason']) for s in run_lines[0]['skipped_days']] == [
            (D3.isoformat(), 'deadline'), (D2.isoformat(), 'deadline'), (D1.isoformat(), 'deadline')]


# ---------------------------------------------------------------------------
# Use-case metadata
# ---------------------------------------------------------------------------


class TestUsecaseMetadata:
    def test_batch_get_is_chunked_in_hundreds_and_keyed_on_the_usecase_record(self, harness):
        ids = [f'0192a000-0000-7000-8000-{i:012d}' for i in range(250)]
        records = [{'pk': 'USECASES', 'sk': f'USECASE#{uid}', 'name': f'uc {i}', 'application_id': APP_A}
                   for i, uid in enumerate(ids)]
        h = harness(usage={D1: {uid: 1.0 for uid in ids[:200]}, D2: {uid: 1.0 for uid in ids[150:]}},
                    records=records)
        run({'days': [D2.isoformat(), D1.isoformat()]})
        assert [len(call) for call in h.resource.batch_get_calls] == [100, 100, 50]
        requested = {key['sk'] for call in h.resource.batch_get_calls for key in call}
        assert requested == {f'USECASE#{uid}' for uid in ids}
        assert all(key['pk'] == 'USECASES' for call in h.resource.batch_get_calls for key in call)
        # one file per use case, all under APP_A, and the app row sums 250 use cases
        assert len([k for k in h.s3.objects if k.startswith(f'{LEDGER_PREFIX}{APP_A}/')]) == 251

    def test_no_usage_means_no_batch_get(self, harness):
        h = harness(usage={})
        run()
        assert h.resource.batch_get_calls == []

    def test_metadata_fields_reach_the_rows(self, harness):
        h = harness()
        run()
        assert rows_of(h, UC_C_KEY)[0].application_id is None
        assert rows_of(h, UC_D_KEY)[0].application_id == APP_B

    def test_unprocessed_keys_are_retried(self, harness):
        """DynamoDB may hand back UnprocessedKeys; the loader must re-request them."""
        h = harness(usage={D1: {UC_A: 1.0, UC_D: 1.0}})
        real = h.resource.batch_get_item
        state = {'first': True}

        def flaky(RequestItems, **kwargs):  # noqa: N803
            keys = list(RequestItems[TABLE]['Keys'])
            if state['first'] and len(keys) == 2:
                state['first'] = False
                partial = real(RequestItems={TABLE: {'Keys': keys[:1]}})
                partial['UnprocessedKeys'] = {TABLE: {'Keys': keys[1:]}}
                return partial
            return real(RequestItems=RequestItems, **kwargs)

        h.resource.batch_get_item = flaky
        meta = cost_collector.load_usecase_meta(h.resource, TABLE, [UC_A, UC_D])
        assert set(meta) == {UC_A, UC_D}
        assert meta[UC_A].application_id == APP_A and meta[UC_A].name == 'Login'
        assert meta[UC_D].application_id == APP_B

    def test_unknown_ids_are_absent_from_meta(self, harness):
        h = harness()
        meta = cost_collector.load_usecase_meta(h.resource, TABLE, [UC_A, GHOST])
        assert set(meta) == {UC_A}

    def test_unprocessed_keys_that_never_drain_fail_the_run(self, harness, monkeypatch):
        h = harness()
        monkeypatch.setattr(cost_collector.time, 'sleep', lambda _s: None)
        h.resource.batch_get_item = lambda RequestItems, **_: {  # noqa: N803
            'Responses': {TABLE: []}, 'UnprocessedKeys': {TABLE: {'Keys': RequestItems[TABLE]['Keys']}}}
        with pytest.raises(RuntimeError, match='unprocessed'):
            cost_collector.load_usecase_meta(h.resource, TABLE, [UC_A])


class TestKeyMapping:
    def test_dimension_key_round_trips_through_the_ledger_key(self):
        row_uc = LedgerRow(date=D1, application_id=APP_A, collected_at='x')
        row_unassigned = LedgerRow(date=D1, collected_at='x')
        for dimension_key, row, expected in [
            (OVERALL_DIMENSION_KEY, row_unassigned, OVERALL_KEY),
            (application_dimension_key(APP_A), row_unassigned, APP_A_KEY),
            (usecase_dimension_key(UC_A), row_uc, UC_A_KEY),
            (usecase_dimension_key(UC_C), row_unassigned, UC_C_KEY),
        ]:
            assert cost_collector._ledger_key_for(dimension_key, row) == expected
            assert cost_collector._dimension_key_of(expected) == dimension_key

    def test_unknown_dimension_key_raises(self):
        with pytest.raises(ValueError, match='unknown dimension key'):
            cost_collector._ledger_key_for('TEMPLATE#x', LedgerRow(date=D1, collected_at='x'))

    @pytest.mark.parametrize('key', [
        'other/overall.ndjson', f'{LEDGER_PREFIX}overall.json', f'{LEDGER_PREFIX}a/b/c.ndjson',
        f'{LEDGER_PREFIX}.ndjson', f'{LEDGER_PREFIX}/x.ndjson',
    ])
    def test_foreign_keys_have_no_dimension(self, key):
        assert cost_collector._dimension_key_of(key) is None


class TestDefaultSeams:
    def test_clients_come_from_boto3(self, monkeypatch):
        boto = MagicMock()
        monkeypatch.setattr(cost_collector, 'boto3', boto)
        assert cost_collector._dynamodb() is boto.resource.return_value
        boto.resource.assert_called_once_with('dynamodb')
        assert cost_collector._lambda_client() is boto.client.return_value
        boto.client.assert_called_once_with('lambda')

    def test_s3_client_is_the_ledger_modules(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(cost_collector, 'get_s3_client', lambda: sentinel)
        assert cost_collector._s3_client() is sentinel

    def test_now_is_utc(self):
        assert cost_collector._now().tzinfo == UTC


# ---------------------------------------------------------------------------
# S3 conflicts
# ---------------------------------------------------------------------------


class TestConditionalWrites:
    def test_lost_race_is_retried_once_and_merges_the_concurrent_row(self, harness):
        h = harness()
        other = LedgerRow(date=dt.date(2026, 10, 20), collected_at='other-writer',
                          cost=[{'service': NOVA_ACT_SERVICE, 'cost': 3.0}], buckets={})
        h.s3.race_once[OVERALL_KEY] = (other.model_dump_json() + '\n').encode()
        report = run()
        puts = [c for c in h.s3.put_calls if c['Key'] == OVERALL_KEY]
        assert len(puts) == 2
        assert puts[0]['IfNoneMatch'] == '*' and puts[1]['IfMatch'] is not None
        rows = rows_of(h, OVERALL_KEY)
        assert [row.date for row in rows] == [other.date, *LOOKBACK]
        assert report.files_written == 7
        # the summary was computed from the merged file, so the concurrent row counts
        summary = CostSummary.from_item(summary_item(h, OVERALL_DIMENSION_KEY))
        assert summary.days_available == 4

    def test_non_retryable_s3_error_propagates(self, harness):
        h = harness()

        def broken(**_):
            raise _client_error('AccessDenied', 'PutObject', 403)

        h.s3.put_object = broken
        with pytest.raises(ClientError) as excinfo:
            run()
        assert excinfo.value.response['Error']['Code'] == 'AccessDenied'


# ---------------------------------------------------------------------------
# Seams for the compute source (task 12)
# ---------------------------------------------------------------------------


class TestSeams:
    def test_default_sources_is_the_nova_act_source(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(cost_collector, 'create_nova_act_client', lambda: fake_client)
        sources = cost_collector._sources(FakeTable())
        assert [type(s).__name__ for s in sources] == ['NovaActSource']
        assert sources[0].name == NOVA_ACT_SERVICE

    def test_compute_source_is_added_when_enabled_and_bound_to_the_table(self, monkeypatch):
        monkeypatch.setattr(cost_collector, 'create_nova_act_client', lambda: MagicMock())
        monkeypatch.setenv('COMPUTE_COST_ENABLED', 'true')
        table = FakeTable()
        sources = cost_collector._sources(table)
        assert [type(s).__name__ for s in sources] == ['NovaActSource', 'ComputeSource']
        assert sources[1].name == COMPUTE_SERVICE
        assert sources[1]._table is table
        monkeypatch.setenv('COMPUTE_COST_ENABLED', 'false')
        assert [type(s).__name__ for s in cost_collector._sources(table)] == ['NovaActSource']

    def test_default_list_prices_use_the_pricing_api_per_source(self, monkeypatch):
        monkeypatch.setattr(cost_collector, 'list_price_per_hour', lambda code: {'NovaAct': 4.75}[code])
        assert cost_collector._list_prices([FakeSource({})]) == {NOVA_ACT_SERVICE: 4.75}

    def test_source_without_a_pricing_code_has_no_list_price(self):
        class Unknown(FakeSource):
            name = 'something_else'

        assert cost_collector._list_prices([Unknown({})]) == {}

    def test_compute_has_no_list_price(self, monkeypatch):
        """MicroVM list prices are per vCPU-s and GB-s of a VM size the source does not know; stays 0."""
        monkeypatch.setattr(cost_collector, 'list_price_per_hour', lambda code: {'NovaAct': 4.75}[code])
        assert cost_collector._list_prices([FakeSource({}), FakeComputeSource()]) == {NOVA_ACT_SERVICE: 4.75}

    def test_lambda_init_is_the_first_import(self):
        import ast
        with open(cost_collector.__file__, encoding='utf-8') as fh:
            tree = ast.parse(fh.read())
        first = next(node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)))
        assert isinstance(first, ast.Import) and first.names[0].name == 'lambda_init'


# ---------------------------------------------------------------------------
# Compute source in the collector (task 12)
# ---------------------------------------------------------------------------


class TestBilledForDay:
    def test_plain_source_uses_billed_cost(self, harness):
        h = harness()
        bill = cost_collector._billed_for_day(D1, [h.source])
        assert bill.seconds == {NOVA_ACT_SERVICE: (40.0, True)}
        assert bill.launches == {}
        assert bill.total() == pytest.approx(40.0)
        assert h.billing.calls == [(D1, FakeSource.ce_filter)]
        assert h.grouped_billing.calls == []

    def test_execution_metered_source_sums_grouped_bill_per_allocation_key(self, harness):
        h = harness(compute=FakeComputeSource())
        bill = cost_collector._billed_for_day(D3, [h.source, h.compute])
        assert bill.seconds[NOVA_ACT_SERVICE] == (10.0, False)
        assert bill.seconds[COMPUTE_SERVICE] == (pytest.approx(1.5), False)   # vCPU 1.0 + memory 0.5; GB-Second ignored
        assert bill.launches == {COMPUTE_SERVICE: pytest.approx(0.3)}
        assert bill.total() == pytest.approx(11.8)
        assert h.grouped_billing.calls == [(D3, COMPUTE_FILTER)]
        assert h.billing.calls == [(D3, FakeSource.ce_filter)]   # one plain call for Nova Act, one grouped for compute

    def test_grouped_estimated_flag_comes_from_the_matched_groups(self, harness):
        h = harness(compute=FakeComputeSource())
        bill = cost_collector._billed_for_day(D1, [h.compute])
        assert bill.seconds[COMPUTE_SERVICE] == (3.0, True)
        assert bill.launches[COMPUTE_SERVICE] == pytest.approx(0.6)

    def test_day_without_matching_groups_is_a_zero_bill(self, harness):
        h = harness(compute=FakeComputeSource(),
                    compute_groups={D1: {'EUC1-Lambda-GB-Second-ARM': _group(9.0), 'EUC1-Request-ARM': _group(1.0)}})
        bill = cost_collector._billed_for_day(D1, [h.compute])
        assert bill.seconds == {COMPUTE_SERVICE: (0.0, False)}
        assert bill.launches == {COMPUTE_SERVICE: 0.0}

    def test_grouped_unavailable_skips_the_day(self, harness):
        h = harness(compute=FakeComputeSource(), compute_groups={D1: None})
        assert cost_collector._billed_for_day(D1, [h.source, h.compute]) is None

    def test_unknown_allocation_key_fails_loudly(self, harness):
        class Odd(FakeComputeSource):
            def classify_usage_type(self, usage_type):
                return 'bytes'

        h = harness(compute=Odd())
        with pytest.raises(ValueError, match='bytes'):
            cost_collector._billed_for_day(D1, [h.compute])


class TestComputeInRun:
    def test_compute_source_gets_the_usecase_ids_nova_act_saw(self, harness):
        h = harness(compute=FakeComputeSource())
        run()
        nova_ids = sorted({uid for day in LOOKBACK for uid in USAGE[day]})
        assert h.compute.calls == [(LOOKBACK, nova_ids)]
        assert h.sources_calls == [h.table]

    def test_compute_rows_split_seconds_and_launch_bills_into_one_entry(self, harness):
        h = harness(compute=FakeComputeSource())
        run()
        uc_a = {row.date: row for row in rows_of(h, UC_A_KEY)}
        uc_d = {row.date: row for row in rows_of(h, UC_D_KEY)}
        overall = {row.date: row for row in rows_of(h, OVERALL_KEY)}
        # D2: seconds bill 2.0 over 400 s (A 100, D 300); launch bill 0.2 over 4 launches (A 1, D 3)
        a = next(c for c in uc_a[D2].cost if c.service == COMPUTE_SERVICE)
        d = next(c for c in uc_d[D2].cost if c.service == COMPUTE_SERVICE)
        assert a.cost == pytest.approx(0.5 + 0.05) and a.usage_seconds == 100.0 and a.launches == 1
        assert d.cost == pytest.approx(1.5 + 0.15) and d.usage_seconds == 300.0 and d.launches == 3
        assert a.list_cost == 0.0   # no compute list price
        compute_overall = next(c for c in overall[D2].cost if c.service == COMPUTE_SERVICE)
        assert compute_overall.cost == pytest.approx(2.2) and compute_overall.launches == 4
        assert overall[D2].total() == pytest.approx(20.0 + 2.2)
        assert overall[D2].buckets.unmetered == pytest.approx(0.0)
        # every row lists both sources, compute first (sorted)
        assert [c.service for c in uc_a[D2].cost] == [COMPUTE_SERVICE, NOVA_ACT_SERVICE]

    def test_launch_only_usecase_is_loaded_and_gets_its_launch_share(self, harness):
        """UC_C launched a VM on D1 that was still running: a launch share, no seconds."""
        h = harness(compute=FakeComputeSource())
        run()
        uc_c = {row.date: row for row in rows_of(h, UC_C_KEY)}
        c = next(c for c in uc_c[D1].cost if c.service == COMPUTE_SERVICE)
        assert c.launches == 1 and c.usage_seconds == 0.0
        assert c.cost == pytest.approx(0.6 / 3)
        requested = {key['sk'] for call in h.resource.batch_get_calls for key in call}
        assert f'USECASE#{UC_C}' in requested

    def test_usecase_unknown_to_nova_act_is_not_metered(self, harness):
        """Known limitation: a use case whose VM issued no Nova Act act is never queried (no scan, no day index)."""
        h = harness(usage={D1: {UC_A: 100.0}},
                    compute=FakeComputeSource(usage={D1: {UC_A: 10.0, UC_D: 10.0}}, launches={D1: {UC_D: 1}}))
        run({'days': [D1.isoformat()]})
        assert h.compute.calls == [([D1], [UC_A])]
        assert not any(UC_D in key for key in h.s3.objects)
        overall = rows_of(h, OVERALL_KEY)[0]
        assert overall.buckets.unmetered == pytest.approx(0.6)   # the launch-keyed part finds no launches

    def test_report_carries_compute_counters_and_both_bill_parts(self, harness):
        h = harness(compute=FakeComputeSource(wallclock_fallbacks=4, running_executions=2))
        report = run()
        assert report.compute_wallclock_fallbacks == 4
        assert report.compute_running_executions == 2
        # Nova Act 70.0 + compute seconds (1.5 + 2.0 + 3.0) + launches (0.3 + 0.2 + 0.6)
        assert report.billed_usd == pytest.approx(70.0 + 6.5 + 1.1)
        assert report.allocated_usd + report.unallocated_usd + report.unmetered_usd == pytest.approx(report.billed_usd)
        assert h.grouped_billing.calls == [(day, COMPUTE_FILTER) for day in LOOKBACK]

    def test_summary_by_source_includes_compute(self, harness):
        h = harness(compute=FakeComputeSource())
        run()
        overall = CostSummary.from_item(summary_item(h, OVERALL_DIMENSION_KEY))
        assert overall.by_source_30d[COMPUTE_SERVICE] == pytest.approx(6.5 + 1.1)
        assert overall.by_source_30d[NOVA_ACT_SERVICE] == pytest.approx(70.0)
        uc_d = CostSummary.from_item(summary_item(h, usecase_dimension_key(UC_D)))
        assert COMPUTE_SERVICE in uc_d.by_source_30d

    def test_compute_bill_without_usage_is_unmetered(self, harness):
        h = harness(compute=FakeComputeSource(usage={}, launches={}))
        report = run({'days': [D3.isoformat()]})
        overall = rows_of(h, OVERALL_KEY)[0]
        assert overall.buckets.unmetered == pytest.approx(1.8)
        assert report.unmetered_usd == pytest.approx(1.8)

    def test_zero_rows_of_touched_dimensions_carry_a_compute_entry(self, harness):
        h = harness(usage={D1: {UC_A: 100.0}}, compute=FakeComputeSource(usage={D1: {UC_A: 10.0}},
                                                                            launches={D1: {UC_A: 1}}))
        run()
        rows = {row.date: row for row in rows_of(h, UC_A_KEY)}
        zero = rows[D3]
        assert [c.service for c in zero.cost] == [COMPUTE_SERVICE, NOVA_ACT_SERVICE]
        assert next(c for c in zero.cost if c.service == COMPUTE_SERVICE).launches == 0
        assert zero.total() == 0.0

    def test_without_compute_source_nothing_changes(self, harness):
        h = harness()
        report = run()
        assert h.grouped_billing.calls == []
        assert report.compute_wallclock_fallbacks == 0 and report.compute_running_executions == 0
        for key in ALL_KEYS:
            assert all([c.service for c in row.cost] == [NOVA_ACT_SERVICE] for row in rows_of(h, key))

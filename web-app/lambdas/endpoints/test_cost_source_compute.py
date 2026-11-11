"""Tests for ``cost_sources.compute``: the MicroVM compute cost source (``FakeTable``, no network).

Design: ``.kiro/docs/cost-allocation/design.md``; task 12.
"""
import datetime as dt
import time
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from boto3.dynamodb.conditions import Key

from cost_billing import service_filter
from cost_models import COMPUTE_SERVICE
from cost_sources import LAUNCHES_KEY, SECONDS_KEY, CostSource, ExecutionMeteredSource, UsageDeadlineExceeded
from cost_sources.compute import (
    COMPUTE_ENABLED_ENV,
    COMPUTE_STEMS_ENV,
    DEFAULT_CE_SERVICE,
    DEFAULT_COMPUTE_STEMS,
    DEFAULT_SNAPSHOT_STEMS,
    SNAPSHOT_STEMS_ENV,
    ComputeSource,
    ComputeUsage,
    compute_source_enabled,
    execution_seconds,
    stems_from_env,
    strip_region_prefix,
    uuid7_bounds,
    uuid7_datetime,
)
from cost_sources.nova_act import NovaActSource
from fake_table import FakeTable
from utils import generate_uuid7

UTC = dt.timezone.utc
D1 = dt.date(2026, 11, 4)
D2 = dt.date(2026, 11, 3)
D0 = dt.date(2026, 11, 5)   # the day after D1: not requested

UC_A = '0192a000-0000-7000-8000-000000000aaa'
UC_B = '0192a000-0000-7000-8000-000000000bbb'
UC_IDLE = '0192a000-0000-7000-8000-000000000ccc'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(value: dt.datetime) -> str:
    return value.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def _at(day: dt.date, hour: int = 10, minute: int = 0, second: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute, second), tzinfo=UTC)


def _uuid7_at(when: dt.datetime, tail: int = 0) -> str:
    """A UUIDv7 whose 48-bit timestamp is ``when`` (ms), version/variant set, random part ``tail``."""
    ms = int(when.timestamp() * 1000)
    value = (ms << 80) | (0x7 << 76) | (0x2 << 62) | (tail & ((1 << 62) - 1))
    hex_str = f'{value:032x}'
    return f'{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}'


_counter = iter(range(1, 1_000_000))


def _execution(usecase_id: str, created: dt.datetime, *, vm: bool = True, vm_seconds: Optional[float] = None,
               wallclock_seconds: Optional[float] = None, started_offset_s: Optional[int] = 5,
               status: str = 'success', **extra) -> Dict:
    """An execution record created at ``created`` (sk = UUIDv7 of that instant).

    ``vm_seconds`` sets ``microvm_started_at``/``microvm_terminated_at``;
    ``wallclock_seconds`` sets ``completed_at`` relative to ``started_at`` (or
    ``created_at`` when ``started_offset_s`` is None); neither = still running.
    """
    item: Dict = {
        'pk': f'USECASE_EXECUTION#{usecase_id}',
        'sk': f'EXECUTION#{_uuid7_at(created, next(_counter))}',
        'status': status,
        'created_at': _ts(created),
    }
    if vm:
        item['microvm_id'] = f'mvm-{next(_counter)}'
    if started_offset_s is not None:
        item['started_at'] = _ts(created + dt.timedelta(seconds=started_offset_s))
    if vm_seconds is not None:
        item['microvm_started_at'] = _ts(created + dt.timedelta(seconds=2))
        item['microvm_terminated_at'] = _ts(created + dt.timedelta(seconds=2 + vm_seconds))
    if wallclock_seconds is not None:
        start = created + dt.timedelta(seconds=started_offset_s or 0)
        item['completed_at'] = _ts(start + dt.timedelta(seconds=wallclock_seconds))
    item.update(extra)
    return item


class RecordingTable(FakeTable):
    """``FakeTable`` that records every ``query`` call."""

    def __init__(self, items=()):
        super().__init__(items)
        self.query_calls: List[Dict] = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return super().query(**kwargs)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (COMPUTE_ENABLED_ENV, COMPUTE_STEMS_ENV, SNAPSHOT_STEMS_ENV, 'COMPUTE_CE_SERVICE'):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Configuration from the environment
# ---------------------------------------------------------------------------


class TestEnvironment:
    def test_disabled_by_default(self):
        assert compute_source_enabled() is False

    @pytest.mark.parametrize('value, expected', [
        ('true', True), ('True', True), (' TRUE ', True), ('false', False), ('', False), ('1', False), ('yes', False),
    ])
    def test_enabled_flag_is_the_literal_true(self, monkeypatch, value, expected):
        monkeypatch.setenv(COMPUTE_ENABLED_ENV, value)
        assert compute_source_enabled() is expected

    def test_defaults_match_the_design(self):
        assert DEFAULT_CE_SERVICE == 'AWS Lambda'
        assert DEFAULT_COMPUTE_STEMS == ('Lambda-MicroVM-vCPU-Second', 'Lambda-MicroVM-Memory-GB-Second')
        assert DEFAULT_SNAPSHOT_STEMS == ('Lambda-MicroVM-Snapshot-Read-GB', 'Lambda-MicroVM-Snapshot-Storage-GB-Hour',
                                          'Lambda-MicroVM-Snapshot-Write-GB')

    def test_stems_from_env_unset_or_blank_gives_the_default(self, monkeypatch):
        assert stems_from_env(COMPUTE_STEMS_ENV, DEFAULT_COMPUTE_STEMS) == DEFAULT_COMPUTE_STEMS
        monkeypatch.setenv(COMPUTE_STEMS_ENV, '  ')
        assert stems_from_env(COMPUTE_STEMS_ENV, DEFAULT_COMPUTE_STEMS) == DEFAULT_COMPUTE_STEMS

    def test_stems_from_env_is_comma_separated_and_trimmed(self, monkeypatch):
        monkeypatch.setenv(COMPUTE_STEMS_ENV, ' Lambda-MicroVM-vCPU-Second, Lambda-MicroVM-Memory-GB-Second ,, ')
        assert stems_from_env(COMPUTE_STEMS_ENV, ()) == ('Lambda-MicroVM-vCPU-Second', 'Lambda-MicroVM-Memory-GB-Second')

    def test_source_reads_service_and_stems_from_env(self, monkeypatch):
        monkeypatch.setenv('COMPUTE_CE_SERVICE', 'AWS Lambda Custom')
        monkeypatch.setenv(COMPUTE_STEMS_ENV, 'Lambda-MicroVM-vCPU-Second')
        monkeypatch.setenv(SNAPSHOT_STEMS_ENV, 'Lambda-MicroVM-Snapshot-Read-GB')
        source = ComputeSource(FakeTable())
        assert source.ce_filter == service_filter('AWS Lambda Custom')
        assert source.classify_usage_type('Lambda-MicroVM-vCPU-Second') == SECONDS_KEY
        assert source.classify_usage_type('Lambda-MicroVM-Memory-GB-Second') is None
        assert source.classify_usage_type('Lambda-MicroVM-Snapshot-Read-GB') == LAUNCHES_KEY
        assert source.classify_usage_type('Lambda-MicroVM-Snapshot-Write-GB') is None

    def test_source_defaults(self):
        source = ComputeSource(FakeTable())
        assert source.name == COMPUTE_SERVICE
        assert source.ce_filter == service_filter('AWS Lambda')
        assert source.ce_filter['Dimensions']['Values'] == ['AWS Lambda']

    def test_overlapping_stems_are_rejected(self):
        with pytest.raises(ValueError, match='overlap'):
            ComputeSource(FakeTable(), compute_stems=('Lambda-MicroVM',), snapshot_stems=('Lambda-MicroVM-Snapshot-Read-GB',))

    def test_empty_stem_lists_are_rejected(self):
        with pytest.raises(ValueError, match='stem'):
            ComputeSource(FakeTable(), compute_stems=())


# ---------------------------------------------------------------------------
# Usage-type classification
# ---------------------------------------------------------------------------


class TestUsageTypes:
    @pytest.mark.parametrize('usage_type, stem', [
        ('EUC1-Lambda-MicroVM-vCPU-Second-ARM', 'Lambda-MicroVM-vCPU-Second-ARM'),
        ('EU-Lambda-MicroVM-Snapshot-Read-GB', 'Lambda-MicroVM-Snapshot-Read-GB'),
        ('Lambda-MicroVM-vCPU-Second', 'Lambda-MicroVM-vCPU-Second'),      # us-east-1 has no prefix
        ('USW2-Lambda-GB-Second', 'Lambda-GB-Second'),
        ('EUC1-Request-ARM', 'EUC1-Request-ARM'),                          # no "Lambda-" follows: untouched
        ('EUC1-USE1-AWS-Out-Bytes', 'EUC1-USE1-AWS-Out-Bytes'),
        ('euc1-Lambda-MicroVM-vCPU-Second', 'euc1-Lambda-MicroVM-vCPU-Second'),  # lower case is not a region code
    ])
    def test_strip_region_prefix(self, usage_type, stem):
        assert strip_region_prefix(usage_type) == stem

    @pytest.mark.parametrize('usage_type, key', [
        ('EUC1-Lambda-MicroVM-vCPU-Second-ARM', SECONDS_KEY),
        ('EUC1-Lambda-MicroVM-Memory-GB-Second-ARM', SECONDS_KEY),
        ('Lambda-MicroVM-vCPU-Second', SECONDS_KEY),
        ('EU-Lambda-MicroVM-Memory-GB-Second', SECONDS_KEY),
        ('EUC1-Lambda-MicroVM-Snapshot-Read-GB', LAUNCHES_KEY),
        ('EUC1-Lambda-MicroVM-Snapshot-Storage-GB-Hour', LAUNCHES_KEY),
        ('Lambda-MicroVM-Snapshot-Write-GB', LAUNCHES_KEY),
        ('EUC1-Lambda-GB-Second-ARM', None),
        ('EUC1-Request', None),
        ('EUC1-DataTransfer-Out-Bytes', None),
        ('EUC1-CloudFront-In-Bytes', None),
        ('', None),
    ])
    def test_classify_usage_type(self, usage_type, key):
        assert ComputeSource(FakeTable()).classify_usage_type(usage_type) == key


# ---------------------------------------------------------------------------
# UUIDv7 day bounds
# ---------------------------------------------------------------------------


class TestUuid7Bounds:
    def test_bounds_are_uuid_shaped(self):
        low, high = uuid7_bounds(D1)
        for value in (low, high):
            assert len(value) == 36 and [len(p) for p in value.split('-')] == [8, 4, 4, 4, 12]
        assert low < high

    def test_low_is_midnight_with_zero_tail_and_high_is_the_last_instant_with_full_tail(self):
        low, high = uuid7_bounds(D1)
        midnight_ms = int(_at(D1, 0).timestamp() * 1000)
        assert int(low.replace('-', ''), 16) == midnight_ms << 80
        next_midnight_ms = int(_at(D0, 0).timestamp() * 1000)
        assert int(high.replace('-', ''), 16) == (next_midnight_ms << 80) - 1

    def test_bounds_contain_exactly_the_days_ids(self):
        low, high = uuid7_bounds(D1)
        assert low <= _uuid7_at(_at(D1, 0, 0, 0)) <= high
        assert low <= _uuid7_at(_at(D1, 23, 59, 59), tail=(1 << 62) - 1) <= high
        assert not (low <= _uuid7_at(_at(D2, 23, 59, 59), tail=(1 << 62) - 1) <= high)
        assert not (low <= _uuid7_at(_at(D0, 0, 0, 0)) <= high)

    def test_consecutive_days_tile_without_gap_or_overlap(self):
        _, high_d2 = uuid7_bounds(D2)
        low_d1, _ = uuid7_bounds(D1)
        assert int(high_d2.replace('-', ''), 16) + 1 == int(low_d1.replace('-', ''), 16)

    def test_a_freshly_generated_uuid7_falls_inside_todays_bounds(self):
        today = dt.datetime.now(UTC).date()
        low, high = uuid7_bounds(today)
        assert low <= generate_uuid7() <= high

    def test_uuid7_datetime_round_trips(self):
        when = _at(D1, 13, 37, 42)
        assert uuid7_datetime(_uuid7_at(when, tail=12345)) == when
        assert uuid7_datetime(_uuid7_at(when)).tzinfo == UTC
        assert uuid7_datetime(f'EXECUTION#{_uuid7_at(when)}') == when   # accepts the sk as stored


# ---------------------------------------------------------------------------
# Seconds per execution record
# ---------------------------------------------------------------------------


class TestExecutionSeconds:
    def test_vm_timestamps_win(self):
        item = _execution(UC_A, _at(D1), vm_seconds=120.0, wallclock_seconds=500.0)
        assert execution_seconds(item) == (120.0, False)

    def test_wallclock_fallback_uses_started_at(self):
        item = _execution(UC_A, _at(D1), wallclock_seconds=300.0)
        assert execution_seconds(item) == (300.0, True)

    def test_wallclock_fallback_without_started_at_uses_created_at(self):
        item = _execution(UC_A, _at(D1), wallclock_seconds=90.0, started_offset_s=None)
        assert execution_seconds(item) == (90.0, True)

    def test_running_execution_has_no_seconds(self):
        assert execution_seconds(_execution(UC_A, _at(D1), status='running')) == (None, False)

    def test_half_written_vm_fields_fall_back_to_wallclock(self):
        item = _execution(UC_A, _at(D1), wallclock_seconds=60.0)
        item['microvm_started_at'] = item['started_at']
        assert execution_seconds(item) == (60.0, True)

    def test_negative_durations_clamp_to_zero(self):
        item = _execution(UC_A, _at(D1), vm_seconds=10.0)
        item['microvm_started_at'], item['microvm_terminated_at'] = item['microvm_terminated_at'], item['microvm_started_at']
        assert execution_seconds(item) == (0.0, False)

    def test_malformed_timestamp_raises(self):
        item = _execution(UC_A, _at(D1), vm_seconds=10.0)
        item['microvm_terminated_at'] = 'yesterday'
        with pytest.raises(ValueError):
            execution_seconds(item)


# ---------------------------------------------------------------------------
# usage_by_day
# ---------------------------------------------------------------------------


def _source(items, **kwargs):
    table = RecordingTable(items)
    return ComputeSource(table, **kwargs), table


class TestUsageByDay:
    def test_vm_seconds_and_launches_per_usecase_per_day(self):
        source, table = _source([
            _execution(UC_A, _at(D1, 9), vm_seconds=100.0),
            _execution(UC_A, _at(D1, 11), vm_seconds=50.0),
            _execution(UC_B, _at(D1, 12), vm_seconds=30.0),
            _execution(UC_A, _at(D2, 8), vm_seconds=70.0),
        ])
        usage = source.usage_by_day([D2, D1], usecase_ids=[UC_A, UC_B])
        assert isinstance(usage, ComputeUsage)
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 150.0, UC_B: 30.0}
        assert usage.by_day[D1].launches_by_usecase == {UC_A: 2, UC_B: 1}
        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 70.0}
        assert usage.by_day[D2].launches_by_usecase == {UC_A: 1}
        assert usage.by_day[D1].unmeasured == 0 and usage.by_day[D2].unmeasured == 0
        assert usage.executions == 4
        assert usage.wallclock_fallbacks == 0 and usage.running_executions == 0
        assert usage.usecases_queried == 2

    def test_deadline_between_usecases_raises_and_stops_querying(self):
        source, table = _source([_execution(UC_A, _at(D1), vm_seconds=1.0)])
        with pytest.raises(UsageDeadlineExceeded) as exc:
            source.usage_by_day([D2, D1], usecase_ids=[UC_A, UC_B], deadline=time.monotonic() - 1)
        assert exc.value.source == COMPUTE_SERVICE
        assert table.query_calls == []

    def test_no_deadline_queries_every_usecase(self):
        source, table = _source([])
        source.usage_by_day([D1], usecase_ids=[UC_A, UC_B], deadline=None)
        assert len(table.query_calls) == 2

    def test_one_paged_query_per_usecase_bounded_by_uuid7(self):
        source, table = _source([_execution(UC_A, _at(D1), vm_seconds=1.0)])
        source.usage_by_day([D2, D1], usecase_ids=[UC_B, UC_A])
        assert len(table.query_calls) == 2
        low, _ = uuid7_bounds(D2)
        _, high = uuid7_bounds(D1)
        expected = [
            Key('pk').eq(f'USECASE_EXECUTION#{uid}') & Key('sk').between(f'EXECUTION#{low}', f'EXECUTION#{high}')
            for uid in (UC_A, UC_B)   # sorted
        ]
        for call, condition in zip(table.query_calls, expected):
            assert call['KeyConditionExpression'].get_expression() == condition.get_expression()
            assert 'ProjectionExpression' in call   # only the fields the metering needs
            assert call['ExpressionAttributeNames'] == {'#s': 'status'}

    def test_records_on_days_inside_the_range_but_not_requested_are_ignored(self):
        middle = dt.date(2026, 11, 2)
        source, _ = _source([
            _execution(UC_A, _at(dt.date(2026, 11, 1)), vm_seconds=10.0),
            _execution(UC_A, _at(middle), vm_seconds=20.0),
            _execution(UC_A, _at(D2), vm_seconds=30.0),
        ])
        usage = source.usage_by_day([dt.date(2026, 11, 1), D2], usecase_ids=[UC_A])
        assert set(usage.by_day) == {dt.date(2026, 11, 1), D2}
        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 30.0}
        assert usage.executions == 2

    def test_records_outside_the_window_are_not_read(self):
        source, _ = _source([
            _execution(UC_A, _at(D0), vm_seconds=10.0),                      # tomorrow
            _execution(UC_A, _at(dt.date(2026, 10, 30)), vm_seconds=10.0),   # before the window
            _execution(UC_A, _at(D1), vm_seconds=5.0),
        ])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A])
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 5.0}
        assert usage.executions == 1

    def test_wallclock_fallback_is_counted(self):
        source, _ = _source([
            _execution(UC_A, _at(D1, 9), vm_seconds=100.0),
            _execution(UC_A, _at(D1, 10), wallclock_seconds=40.0),
            _execution(UC_B, _at(D1, 11), wallclock_seconds=10.0, started_offset_s=None),
        ])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A, UC_B])
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 140.0, UC_B: 10.0}
        assert usage.wallclock_fallbacks == 2

    def test_running_execution_counts_as_a_launch_but_no_seconds(self):
        source, _ = _source([
            _execution(UC_A, _at(D1, 9), vm_seconds=100.0),
            _execution(UC_A, _at(D1, 10), status='running'),
        ])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A])
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 100.0}
        assert usage.by_day[D1].launches_by_usecase == {UC_A: 2}
        assert usage.by_day[D1].unmeasured == 1
        assert usage.running_executions == 1
        assert usage.executions == 2

    def test_records_without_a_vm_are_skipped(self):
        """Pre-MicroVM (``task_arn``) records and launches that failed before ``RunMicrovm`` ran no VM."""
        source, _ = _source([
            _execution(UC_A, _at(D1, 9), vm=False, wallclock_seconds=100.0, task_arn='arn:aws:ecs:…'),
            _execution(UC_A, _at(D1, 10), vm=False, status='failed'),
        ])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A])
        assert usage.by_day[D1].seconds_by_usecase == {}
        assert usage.by_day[D1].launches_by_usecase == {}
        assert usage.executions == 0
        assert usage.executions_without_vm == 2

    def test_wizard_sessions_are_execution_records_under_the_same_partition(self):
        source, _ = _source([
            _execution(UC_A, _at(D1, 9), vm_seconds=600.0, mode='wizard', trigger_type='Wizard',
                       wizard_status='closed'),
        ])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A])
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 600.0}
        assert usage.by_day[D1].launches_by_usecase == {UC_A: 1}

    def test_usecase_without_executions_has_no_entries(self):
        source, table = _source([_execution(UC_A, _at(D1), vm_seconds=1.0)])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A, UC_IDLE])
        assert UC_IDLE not in usage.by_day[D1].seconds_by_usecase
        assert UC_IDLE not in usage.by_day[D1].launches_by_usecase
        assert usage.usecases_queried == 2 and len(table.query_calls) == 2

    def test_usecases_not_handed_in_are_not_queried(self):
        """Known limitation: a use case the earlier sources did not see is invisible (no scan)."""
        source, table = _source([_execution(UC_B, _at(D1), vm_seconds=1.0)])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A])
        assert usage.by_day[D1].seconds_by_usecase == {}
        assert len(table.query_calls) == 1

    def test_duplicate_ids_are_queried_once(self):
        source, table = _source([_execution(UC_A, _at(D1), vm_seconds=1.0)])
        usage = source.usage_by_day([D1], usecase_ids=[UC_A, UC_A])
        assert usage.by_day[D1].launches_by_usecase == {UC_A: 1}
        assert len(table.query_calls) == 1

    def test_no_ids_means_no_queries_but_every_day_present(self):
        source, table = _source([])
        usage = source.usage_by_day([D2, D1], usecase_ids=[])
        assert set(usage.by_day) == {D2, D1}
        assert table.query_calls == []

    def test_empty_days_raise(self):
        with pytest.raises(ValueError, match='at least one day'):
            ComputeSource(FakeTable()).usage_by_day([], usecase_ids=[UC_A])

    def test_follows_last_evaluated_key(self):
        first = _execution(UC_A, _at(D1, 9), vm_seconds=10.0)
        second = _execution(UC_A, _at(D1, 10), vm_seconds=20.0)
        table = MagicMock()
        table.query.side_effect = [
            {'Items': [first], 'LastEvaluatedKey': {'pk': first['pk'], 'sk': first['sk']}},
            {'Items': [second]},
        ]
        usage = ComputeSource(table).usage_by_day([D1], usecase_ids=[UC_A])
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 30.0}
        assert usage.queries == 2
        assert table.query.call_args_list[1].kwargs['ExclusiveStartKey'] == {'pk': first['pk'], 'sk': first['sk']}
        assert 'ExclusiveStartKey' not in table.query.call_args_list[0].kwargs

    def test_dynamodb_errors_propagate(self):
        from botocore.exceptions import ClientError
        table = MagicMock()
        table.query.side_effect = ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException',
                                                         'Message': 'slow down'}}, 'Query')
        with pytest.raises(ClientError):
            ComputeSource(table).usage_by_day([D1], usecase_ids=[UC_A])

    def test_log_line_carries_counts_only(self, caplog):
        source, _ = _source([
            _execution(UC_A, _at(D1, 9), vm_seconds=100.0),
            _execution(UC_A, _at(D1, 10), wallclock_seconds=40.0),
            _execution(UC_A, _at(D1, 11), status='running'),
        ])
        with caplog.at_level('INFO', logger='cost_sources.compute'):
            source.usage_by_day([D1], usecase_ids=[UC_A])
        text = ' '.join(record.getMessage() for record in caplog.records)
        assert 'compute usage collected' in text
        assert '1 use cases' in text and '3 executions' in text
        assert '1 wall-clock fallback' in text and '1 still running' in text
        assert UC_A not in text and 'mvm-' not in text


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_compute_source_is_an_execution_metered_cost_source(self):
        source = ComputeSource(FakeTable())
        assert isinstance(source, CostSource)
        assert isinstance(source, ExecutionMeteredSource)

    def test_nova_act_source_is_not_execution_metered(self):
        source = NovaActSource(MagicMock())
        assert isinstance(source, CostSource)
        assert not isinstance(source, ExecutionMeteredSource)

    def test_module_creates_no_client_at_import(self):
        import cost_sources.compute as module
        assert not hasattr(module, 'boto3')

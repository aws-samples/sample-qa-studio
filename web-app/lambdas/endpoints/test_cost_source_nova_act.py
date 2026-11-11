"""Tests for ``cost_sources.nova_act`` with a fake ``nova-act`` client (no network)."""
import datetime as dt
import logging
import threading
import time
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_models import NOVA_ACT_SERVICE
from cost_sources import CostSource, DayUsage, SourceUsage, UsageDeadlineExceeded
from cost_sources.nova_act import (
    DEFAULT_CE_SERVICE_NAME,
    DEFAULT_WORKERS,
    LIST_ATTEMPTS,
    LIST_WORKERS_ENV,
    NOVA_ACT_REGION,
    PAGE_SIZE,
    PROGRESS_EVERY,
    NovaActSource,
    NovaActUsage,
    create_nova_act_client,
)

UTC = dt.timezone.utc
D1 = dt.date(2026, 11, 2)
D2 = dt.date(2026, 11, 3)
D3 = dt.date(2026, 11, 4)
DAYS = [D3, D2, D1]  # deliberately unsorted; the source must not care

UC_A = '0192a000-0000-7000-8000-000000000aaa'
UC_B = '0192a000-0000-7000-8000-000000000bbb'


def ts(day: dt.date, hour: int = 12, minute: int = 0, second: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


def act(started: dt.datetime, seconds: Optional[float] = 10.0, status: str = 'SUCCEEDED', act_id: str = 'a') -> dict:
    """An ``actSummaries[*]`` entry; ``seconds=None`` omits ``endedAt`` (TIMED_OUT shape)."""
    summary = {'actId': act_id, 'sessionId': 's', 'workflowRunId': 'r', 'status': status, 'startedAt': started}
    if seconds is not None:
        summary['endedAt'] = started + dt.timedelta(seconds=seconds)
    return summary


def throttled(operation: str) -> ClientError:
    return ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'slow down'}}, operation)


def not_found(operation: str) -> ClientError:
    return ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Workflow definition not found'}},
                       operation)


class FakeNovaActClient:
    """Pages ``ListWorkflowDefinitions`` / ``ListActs`` like the real client.

    ``acts[name]`` must already be sorted by ``startedAt`` descending (the real
    API guarantees it); ``page_size`` controls how many acts a page carries so
    tests can force several pages.  ``errors[(operation, call_index)]`` raises
    on the n-th call of that operation (0-based, counting every call).
    """

    def __init__(self, acts: Dict[str, List[dict]], page_size: int = 100, definitions_page_size: int = 100):
        self.acts = acts
        self.page_size = page_size
        self.definitions_page_size = definitions_page_size
        #: ``(operation, call_index)`` or ``(operation, workflowDefinitionName)`` → exception raised once.
        self.errors: Dict[tuple, Exception] = {}
        self.calls: List[dict] = []
        self.meta = MagicMock(region_name=NOVA_ACT_REGION)
        self._lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0

    def _maybe_raise(self, operation: str, name: Optional[str] = None) -> None:
        index = sum(1 for c in self.calls if c['operation'] == operation) - 1
        error = self.errors.pop((operation, index), None)
        if error is None and name is not None:
            error = self.errors.pop((operation, name), None)
        if error is not None:
            raise error

    def list_workflow_definitions(self, **kwargs) -> dict:
        with self._lock:
            self.calls.append({'operation': 'ListWorkflowDefinitions', **kwargs})
            self._maybe_raise('ListWorkflowDefinitions')
        names = sorted(self.acts)
        start = int(kwargs.get('nextToken') or 0)
        end = start + self.definitions_page_size
        page = {
            'workflowDefinitionSummaries': [
                {'workflowDefinitionArn': f'arn:aws:nova-act:us-east-1:1:workflow-definition/{n}',
                 'workflowDefinitionName': n, 'createdAt': ts(D1), 'status': 'ACTIVE'}
                for n in names[start:end]
            ],
        }
        if end < len(names):
            page['nextToken'] = str(end)
        return page

    def list_acts(self, **kwargs) -> dict:
        name = kwargs['workflowDefinitionName']
        with self._lock:
            self.calls.append({'operation': 'ListActs', **kwargs})
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            with self._lock:
                self._maybe_raise('ListActs', name)
            time.sleep(self.page_delay)
            assert kwargs['sortOrder'] == 'Descending'
            assert kwargs['maxResults'] <= 100
            if name not in self.acts:
                raise not_found('ListActs')
            start = int(kwargs.get('nextToken') or 0)
            end = start + self.page_size
            page = {'actSummaries': self.acts[name][start:end]}
            if end < len(self.acts[name]):
                page['nextToken'] = str(end)
            return page
        finally:
            with self._lock:
                self.in_flight -= 1

    #: Seconds each ``ListActs`` page takes (0 by default; concurrency tests raise it).
    page_delay = 0.0

    def act_pages(self, name: Optional[str] = None) -> int:
        return sum(1 for c in self.calls
                   if c['operation'] == 'ListActs' and (name is None or c['workflowDefinitionName'] == name))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv('NOVA_ACT_CE_SERVICE_NAME', raising=False)


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch('cost_sources.nova_act._sleep') as sleep:
        yield sleep


def _big_account(definitions: int = 30, acts_per_definition: int = 7, page_size: int = 3) -> FakeNovaActClient:
    """Many definitions with several pages each, so concurrency and progress logging are exercised."""
    acts = {f'uc-{i:03d}': [act(ts(D2, 12, 0, 59 - j), 1, act_id=f'{i}-{j}') for j in range(acts_per_definition)]
            for i in range(definitions)}
    return FakeNovaActClient(acts, page_size=page_size)


# ---------------------------------------------------------------------------
# Concurrency, progress, deadline
# ---------------------------------------------------------------------------


class TestFanOut:
    def test_default_workers_from_constant_and_env(self, monkeypatch):
        assert DEFAULT_WORKERS == 8
        assert NovaActSource(FakeNovaActClient({})).workers == DEFAULT_WORKERS
        monkeypatch.setenv(LIST_WORKERS_ENV, '3')
        assert NovaActSource(FakeNovaActClient({})).workers == 3
        assert NovaActSource(FakeNovaActClient({}), workers=2).workers == 2

    @pytest.mark.parametrize('bad', ['0', '-1', 'eight'])
    def test_invalid_workers_are_rejected(self, monkeypatch, bad):
        monkeypatch.setenv(LIST_WORKERS_ENV, bad)
        with pytest.raises(ValueError, match=LIST_WORKERS_ENV):
            NovaActSource(FakeNovaActClient({}))

    def test_definitions_are_paged_concurrently(self):
        client = _big_account(definitions=12, acts_per_definition=1, page_size=1)
        client.page_delay = 0.02
        NovaActSource(client, workers=4).usage_by_day(DAYS)
        assert client.max_in_flight > 1
        assert client.max_in_flight <= 4

    def test_result_is_identical_regardless_of_worker_count(self):
        serial = NovaActSource(_big_account(), workers=1).usage_by_day(DAYS)
        parallel = NovaActSource(_big_account(), workers=8).usage_by_day(DAYS)
        assert serial == parallel
        assert parallel.definitions == 30 and parallel.pages == 90 and parallel.acts == 210
        assert list(parallel.by_day[D2].seconds_by_usecase) == sorted(parallel.by_day[D2].seconds_by_usecase)

    def test_unknown_definition_mid_run_is_skipped_under_concurrency(self):
        client = _big_account(definitions=10)
        client.errors[('ListActs', 'uc-004')] = not_found('ListActs')
        usage = NovaActSource(client, workers=4).usage_by_day(DAYS)
        assert usage.skipped_definitions == 1
        assert 'uc-004' not in usage.by_day[D2].seconds_by_usecase
        assert len(usage.by_day[D2].seconds_by_usecase) == 9

    def test_other_errors_propagate_under_concurrency(self):
        client = _big_account(definitions=10)
        client.errors[('ListActs', 'uc-007')] = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'ListActs')
        with pytest.raises(ClientError) as exc:
            NovaActSource(client, workers=4).usage_by_day(DAYS)
        assert exc.value.response['Error']['Code'] == 'AccessDeniedException'

    def test_progress_is_logged_every_n_definitions_with_counts_only(self, caplog):
        assert PROGRESS_EVERY == 25
        client = _big_account(definitions=60)
        with caplog.at_level(logging.INFO, logger='cost_sources.nova_act'):
            NovaActSource(client, workers=4).usage_by_day(DAYS)
        progress = [r.getMessage() for r in caplog.records if 'progress' in r.getMessage()]
        assert len(progress) == 2  # after 25 and 50 of 60
        assert '25/60' in progress[0] and '50/60' in progress[1]
        assert 'uc-0' not in ' '.join(progress)

    def test_deadline_exceeded_raises_and_stops_paging(self):
        client = _big_account(definitions=40, acts_per_definition=3, page_size=1)
        client.page_delay = 0.01
        clock = time.monotonic
        with pytest.raises(UsageDeadlineExceeded) as exc:
            NovaActSource(client, workers=2).usage_by_day(DAYS, deadline=clock() + 0.05)
        assert 'nova_act' in str(exc.value)
        pages_at_raise = client.act_pages()
        time.sleep(0.1)
        assert client.act_pages() <= pages_at_raise + 2  # in-flight pages finish, nothing new is started
        assert client.act_pages() < 120

    def test_no_deadline_means_no_limit(self):
        usage = NovaActSource(_big_account(definitions=5), workers=2).usage_by_day(DAYS, deadline=None)
        assert usage.definitions == 5

    def test_deadline_in_the_past_raises_before_listing_acts(self):
        client = _big_account(definitions=5)
        with pytest.raises(UsageDeadlineExceeded):
            NovaActSource(client, workers=2).usage_by_day(DAYS, deadline=time.monotonic() - 1)
        assert client.act_pages() == 0


# ---------------------------------------------------------------------------
# Protocol, name, ce_filter, client factory
# ---------------------------------------------------------------------------


class TestInterface:
    def test_is_a_cost_source(self):
        source = NovaActSource(FakeNovaActClient({}))
        assert isinstance(source, CostSource)
        assert source.name == NOVA_ACT_SERVICE

    def test_ce_filter_defaults_to_novaact(self):
        assert NovaActSource(FakeNovaActClient({})).ce_filter == {
            'Dimensions': {'Key': 'SERVICE', 'Values': [DEFAULT_CE_SERVICE_NAME]},
        }
        assert DEFAULT_CE_SERVICE_NAME == 'NovaAct'

    def test_ce_filter_reads_env(self, monkeypatch):
        monkeypatch.setenv('NOVA_ACT_CE_SERVICE_NAME', 'Amazon Nova Act')
        assert NovaActSource(FakeNovaActClient({})).ce_filter['Dimensions']['Values'] == ['Amazon Nova Act']

    def test_ce_filter_explicit_argument_wins_over_env(self, monkeypatch):
        monkeypatch.setenv('NOVA_ACT_CE_SERVICE_NAME', 'FromEnv')
        source = NovaActSource(FakeNovaActClient({}), service_name='Explicit')
        assert source.ce_filter['Dimensions']['Values'] == ['Explicit']

    def test_create_client_always_uses_us_east_1(self):
        assert NOVA_ACT_REGION == 'us-east-1'
        with patch('cost_sources.nova_act.boto3.client') as client:
            create_nova_act_client()
        client.assert_called_once_with('nova-act', region_name='us-east-1')

    def test_page_size_is_the_api_maximum(self):
        assert PAGE_SIZE == 100


# ---------------------------------------------------------------------------
# usage_by_day
# ---------------------------------------------------------------------------


class TestUsageByDay:
    def test_empty_account(self):
        client = FakeNovaActClient({})
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert isinstance(usage, NovaActUsage)
        assert isinstance(usage, SourceUsage)
        assert set(usage.by_day) == {D1, D2, D3}
        assert all(day.seconds_by_usecase == {} and day.unmeasured == 0 for day in usage.by_day.values())
        assert (usage.definitions, usage.pages, usage.acts, usage.acts_without_end,
                usage.skipped_definitions) == (0, 0, 0, 0, 0)
        assert client.act_pages() == 0

    def test_rejects_empty_days(self):
        with pytest.raises(ValueError):
            NovaActSource(FakeNovaActClient({})).usage_by_day([])

    def test_sums_seconds_per_usecase_per_start_day(self):
        client = FakeNovaActClient({
            UC_A: [act(ts(D3, 10), 30), act(ts(D2, 9), 20), act(ts(D2, 8), 5)],
            UC_B: [act(ts(D1, 23), 7)],
        })
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D3].seconds_by_usecase == {UC_A: 30.0}
        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 25.0}
        assert usage.by_day[D1].seconds_by_usecase == {UC_B: 7.0}
        assert usage.definitions == 2
        assert usage.acts == 4
        assert usage.pages == 2

    def test_seconds_by_usecase_is_a_plain_dict_without_defaultdict_side_effects(self):
        usage = NovaActSource(FakeNovaActClient({UC_A: [act(ts(D2), 1)]})).usage_by_day(DAYS)
        day = usage.by_day[D2]
        assert type(day.seconds_by_usecase) is dict
        assert day.seconds_by_usecase.get(UC_B) is None
        assert UC_B not in day.seconds_by_usecase

    def test_act_spanning_midnight_is_attributed_to_its_start_day(self):
        started = ts(D2, 23, 59, 30)
        client = FakeNovaActClient({UC_A: [act(started, 90)]})  # ends 00:01:00 on D3
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 90.0}
        assert usage.by_day[D3].seconds_by_usecase == {}

    def test_start_day_is_the_utc_day(self):
        # 2026-11-03 23:30 at UTC-2 is 2026-11-04 01:30 UTC → attributed to D3.
        started = dt.datetime(2026, 11, 3, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-2)))
        usage = NovaActSource(FakeNovaActClient({UC_A: [act(started, 10)]})).usage_by_day(DAYS)
        assert usage.by_day[D3].seconds_by_usecase == {UC_A: 10.0}
        assert usage.by_day[D2].seconds_by_usecase == {}

    def test_naive_timestamps_are_treated_as_utc(self):
        started = dt.datetime(2026, 11, 3, 12, 0)
        summary = {'actId': 'a', 'sessionId': 's', 'workflowRunId': 'r', 'status': 'SUCCEEDED',
                   'startedAt': started, 'endedAt': started + dt.timedelta(seconds=4)}
        usage = NovaActSource(FakeNovaActClient({UC_A: [summary]})).usage_by_day(DAYS)
        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 4.0}

    def test_acts_newer_than_the_range_are_read_but_not_attributed(self):
        today = D3 + dt.timedelta(days=1)
        client = FakeNovaActClient({UC_A: [act(ts(today, 1), 100), act(ts(D3, 1), 5)]})
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D3].seconds_by_usecase == {UC_A: 5.0}
        assert sum(sum(d.seconds_by_usecase.values()) for d in usage.by_day.values()) == 5.0
        assert usage.acts == 1  # only in-window acts count

    def test_days_inside_the_range_but_not_requested_are_not_attributed(self):
        client = FakeNovaActClient({UC_A: [act(ts(D3), 1), act(ts(D2), 2), act(ts(D1), 3)]})
        usage = NovaActSource(client).usage_by_day([D3, D1])

        assert set(usage.by_day) == {D1, D3}
        assert usage.by_day[D3].seconds_by_usecase == {UC_A: 1.0}
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 3.0}
        assert usage.acts == 2

    def test_multi_page_paging_follows_next_token(self):
        acts = [act(ts(D2, 12, 0, 59 - i), 1, act_id=f'a{i}') for i in range(7)]
        client = FakeNovaActClient({UC_A: acts}, page_size=3)
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 7.0}
        assert client.act_pages(UC_A) == 3
        assert usage.pages == 3
        tokens = [c.get('nextToken') for c in client.calls if c['operation'] == 'ListActs']
        assert tokens == [None, '3', '6']

    def test_definitions_are_paged_too(self):
        names = {f'uc-{i:02d}': [act(ts(D2), 1)] for i in range(5)}
        client = FakeNovaActClient(names, definitions_page_size=2)
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.definitions == 5
        assert sum(1 for c in client.calls if c['operation'] == 'ListWorkflowDefinitions') == 3
        assert all(c['maxResults'] == PAGE_SIZE for c in client.calls)
        assert usage.by_day[D2].seconds_by_usecase == {name: 1.0 for name in names}

    def test_early_stop_at_first_act_older_than_the_range(self):
        older = [act(ts(D1 - dt.timedelta(days=1 + i)), 1000, act_id=f'old{i}') for i in range(10)]
        acts = [act(ts(D3), 1), act(ts(D2), 2), act(ts(D1, 0, 0, 0), 3)] + older
        client = FakeNovaActClient({UC_A: acts}, page_size=4)
        usage = NovaActSource(client).usage_by_day(DAYS)

        # 13 acts at 4/page = 4 pages without the stop; the first old act is on page 1.
        assert client.act_pages(UC_A) == 1
        assert usage.by_day[D1].seconds_by_usecase == {UC_A: 3.0}  # midnight at min(days) is inside
        assert sum(sum(d.seconds_by_usecase.values()) for d in usage.by_day.values()) == 6.0
        assert usage.acts == 3

    def test_early_stop_ends_exactly_when_the_old_act_is_the_first_of_a_page(self):
        acts = [act(ts(D3), 1), act(ts(D2), 2), act(ts(D1 - dt.timedelta(days=1)), 99)]
        client = FakeNovaActClient({UC_A: acts}, page_size=2)
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert client.act_pages(UC_A) == 2  # page 2 starts with the old act → stop, no page 3
        assert usage.acts == 2

    def test_no_early_stop_while_every_act_is_in_range(self):
        acts = [act(ts(D2, 12, 0, 9 - i), 1, act_id=f'a{i}') for i in range(10)]
        client = FakeNovaActClient({UC_A: acts}, page_size=5)
        NovaActSource(client).usage_by_day(DAYS)
        assert client.act_pages(UC_A) == 2  # both pages read, nextToken absent on the last → done

    def test_missing_ended_at_counts_as_unmeasured(self, caplog):
        client = FakeNovaActClient({
            UC_A: [act(ts(D3), 10), act(ts(D3), None, status='TIMED_OUT', act_id='t1'),
                   act(ts(D2), None, status='TIMED_OUT', act_id='t2')],
            UC_B: [act(ts(D2), None, status='RUNNING', act_id='t3')],
        })
        with caplog.at_level(logging.WARNING, logger='cost_sources.nova_act'):
            usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D3].seconds_by_usecase == {UC_A: 10.0}
        assert usage.by_day[D3].unmeasured == 1
        assert usage.by_day[D2].seconds_by_usecase == {}
        assert usage.by_day[D2].unmeasured == 2
        assert usage.by_day[D1].unmeasured == 0
        assert usage.acts_without_end == 3
        assert usage.acts == 4
        warnings = [r for r in caplog.records if 'endedAt' in r.getMessage()]
        assert len(warnings) == 1, 'logged once per run'
        assert '3' in warnings[0].getMessage()

    def test_no_warning_when_every_act_has_ended(self, caplog):
        with caplog.at_level(logging.WARNING, logger='cost_sources.nova_act'):
            NovaActSource(FakeNovaActClient({UC_A: [act(ts(D2), 1)]})).usage_by_day(DAYS)
        assert not [r for r in caplog.records if 'endedAt' in r.getMessage()]

    def test_missing_ended_at_older_than_range_does_not_count(self):
        client = FakeNovaActClient({UC_A: [act(ts(D1 - dt.timedelta(days=5)), None, status='TIMED_OUT')]})
        usage = NovaActSource(client).usage_by_day(DAYS)
        assert usage.acts_without_end == 0

    def test_run_summary_is_logged_without_response_payloads(self, caplog):
        client = FakeNovaActClient({UC_A: [act(ts(D2), 1, act_id='secret-act-id')]})
        with caplog.at_level(logging.INFO, logger='cost_sources.nova_act'):
            NovaActSource(client).usage_by_day(DAYS)
        messages = [r.getMessage() for r in caplog.records]
        summary = [m for m in messages if 'definitions' in m and 'pages' in m]
        assert len(summary) == 1
        assert 'secret-act-id' not in ' '.join(messages)
        assert UC_A not in ' '.join(messages)


# ---------------------------------------------------------------------------
# Errors: throttling retry, unknown definition
# ---------------------------------------------------------------------------


class TestErrors:
    def test_throttled_list_acts_is_retried_with_exponential_backoff(self, _no_sleep):
        client = FakeNovaActClient({UC_A: [act(ts(D2), 1)]})
        client.errors[('ListActs', 0)] = throttled('ListActs')
        client.errors[('ListActs', 1)] = throttled('ListActs')
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 1.0}
        assert [c.args[0] for c in _no_sleep.call_args_list] == [1, 2]
        assert usage.pages == 1  # retries are not pages

    def test_throttled_list_workflow_definitions_is_retried(self, _no_sleep):
        client = FakeNovaActClient({UC_A: [act(ts(D2), 1)]})
        client.errors[('ListWorkflowDefinitions', 0)] = throttled('ListWorkflowDefinitions')
        usage = NovaActSource(client).usage_by_day(DAYS)
        assert usage.definitions == 1
        assert _no_sleep.call_count == 1

    def test_throttling_gives_up_after_the_attempt_limit(self, _no_sleep):
        client = FakeNovaActClient({UC_A: [act(ts(D2), 1)]})
        for i in range(LIST_ATTEMPTS):
            client.errors[('ListActs', i)] = throttled('ListActs')
        with pytest.raises(ClientError) as exc:
            NovaActSource(client).usage_by_day(DAYS)
        assert exc.value.response['Error']['Code'] == 'ThrottlingException'
        assert _no_sleep.call_count == LIST_ATTEMPTS - 1

    def test_other_client_errors_propagate_without_retry(self, _no_sleep):
        client = FakeNovaActClient({UC_A: [act(ts(D2), 1)]})
        client.errors[('ListActs', 0)] = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'ListActs')
        with pytest.raises(ClientError):
            NovaActSource(client).usage_by_day(DAYS)
        _no_sleep.assert_not_called()

    def test_unknown_definition_is_skipped_and_the_rest_continues(self, caplog):
        client = FakeNovaActClient({UC_A: [act(ts(D2), 1)], UC_B: [act(ts(D2), 2)]})
        client.errors[('ListActs', UC_A)] = not_found('ListActs')  # keyed by name: paging is concurrent
        with caplog.at_level(logging.WARNING, logger='cost_sources.nova_act'):
            usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D2].seconds_by_usecase == {UC_B: 2.0}
        assert usage.definitions == 2
        assert usage.skipped_definitions == 1
        assert any('not found' in r.getMessage().lower() for r in caplog.records)

    def test_unknown_definition_mid_paging_keeps_the_pages_already_read(self):
        acts = [act(ts(D2, 12, 0, 5 - i), 1, act_id=f'a{i}') for i in range(6)]
        client = FakeNovaActClient({UC_A: acts}, page_size=3)
        client.errors[('ListActs', 1)] = not_found('ListActs')
        usage = NovaActSource(client).usage_by_day(DAYS)

        assert usage.by_day[D2].seconds_by_usecase == {UC_A: 3.0}
        assert usage.skipped_definitions == 1
        assert usage.pages == 1


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class TestResultTypes:
    def test_day_usage_defaults(self):
        day = DayUsage()
        assert day.seconds_by_usecase == {}
        assert day.unmeasured == 0

    def test_day_usage_instances_do_not_share_the_dict(self):
        a, b = DayUsage(), DayUsage()
        a.seconds_by_usecase['x'] = 1.0
        assert b.seconds_by_usecase == {}

    def test_total_seconds(self):
        assert DayUsage(seconds_by_usecase={UC_A: 1.5, UC_B: 2.5}).total_seconds() == 4.0

    def test_nova_act_usage_counters_default_to_zero(self):
        usage = NovaActUsage(by_day={})
        assert (usage.definitions, usage.pages, usage.acts, usage.acts_without_end,
                usage.skipped_definitions) == (0, 0, 0, 0, 0)

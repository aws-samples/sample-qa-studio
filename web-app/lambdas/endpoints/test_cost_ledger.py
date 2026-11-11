"""Unit tests for cost_ledger: S3 key layout, NDJSON read, conditional upsert and tail."""
import datetime as dt
import io
import logging
import os
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import cost_ledger
from cost_ledger import (
    APPLICATION_DIMENSION,
    LEDGER_CONTENT_TYPE,
    LEDGER_PREFIX,
    MAX_PUT_ATTEMPTS,
    OVERALL_DIMENSION,
    UNASSIGNED_FOLDER,
    USECASE_DIMENSION,
    ledger_key,
    read,
    read_tail,
    upsert_rows,
)
from cost_models import LedgerRow, ServiceCost

ENDPOINTS_DIR = os.path.dirname(os.path.abspath(__file__))
BUCKET = 'test-artefacts'
KEY = 'cost_allocation/overall.ndjson'
APP = '0192a3b4-0000-7000-8000-000000000001'
UC = '0192a3b4-0000-7000-8000-00000000000a'


def _row(day, cost=1.0, collected_at='2026-11-05T06:00:00Z', application_id=None):
    return LedgerRow(
        date=dt.date.fromisoformat(day), estimated=False, application_id=application_id,
        cost=[ServiceCost(service='nova_act', cost=cost, list_cost=cost, usage_seconds=60.0)],
        collected_at=collected_at,
    )


def _body(rows):
    return ''.join(row.model_dump_json() + '\n' for row in rows).encode('utf-8')


def _client_error(code, operation):
    return ClientError({'Error': {'Code': code, 'Message': code}}, operation)


def _get_object_response(body: bytes, etag='"etag-1"'):
    return {'Body': io.BytesIO(body), 'ETag': etag, 'ContentType': LEDGER_CONTENT_TYPE}


@pytest.fixture(autouse=True)
def _bucket_env(monkeypatch):
    monkeypatch.setenv('S3_BUCKET', BUCKET)
    monkeypatch.delenv('BUCKET_NAME', raising=False)
    monkeypatch.setattr(cost_ledger, '_s3_client', None)


def _s3_with_object(rows, etag='"etag-1"'):
    s3 = MagicMock()
    s3.get_object.return_value = _get_object_response(_body(rows), etag)
    return s3


def _s3_without_object():
    s3 = MagicMock()
    s3.get_object.side_effect = _client_error('NoSuchKey', 'GetObject')
    return s3


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


class TestLedgerKey:
    def test_overall(self):
        assert ledger_key(OVERALL_DIMENSION) == 'cost_allocation/overall.ndjson'

    def test_application(self):
        assert ledger_key(APPLICATION_DIMENSION, APP) == f'cost_allocation/{APP}/raw.ndjson'

    def test_usecase_under_its_application(self):
        assert ledger_key(USECASE_DIMENSION, APP, UC) == f'cost_allocation/{APP}/{UC}.ndjson'

    @pytest.mark.parametrize('application_id', [None, ''])
    def test_usecase_without_application_is_unassigned(self, application_id):
        assert ledger_key(USECASE_DIMENSION, application_id, UC) == f'cost_allocation/_unassigned/{UC}.ndjson'
        assert UNASSIGNED_FOLDER == '_unassigned'

    def test_reassigned_usecase_gets_a_new_file(self):
        other_app = '0192a3b4-0000-7000-8000-000000000002'
        assert ledger_key(USECASE_DIMENSION, APP, UC) != ledger_key(USECASE_DIMENSION, other_app, UC)

    def test_all_keys_share_the_prefix(self):
        assert LEDGER_PREFIX == 'cost_allocation/'
        for key in (ledger_key(OVERALL_DIMENSION), ledger_key(APPLICATION_DIMENSION, APP),
                    ledger_key(USECASE_DIMENSION, APP, UC), ledger_key(USECASE_DIMENSION, None, UC)):
            assert key.startswith(LEDGER_PREFIX)
            assert key.endswith('.ndjson')

    @pytest.mark.parametrize('args', [
        ('unknown',),
        (OVERALL_DIMENSION, APP),
        (APPLICATION_DIMENSION,),
        (APPLICATION_DIMENSION, APP, UC),
        (USECASE_DIMENSION, UC),
        (USECASE_DIMENSION, APP, UC, 'extra'),
    ])
    def test_wrong_dimension_or_arity_raises(self, args):
        with pytest.raises(ValueError):
            ledger_key(*args)

    @pytest.mark.parametrize('bad_id', ['', '../x', 'a/b', 'a b', 'ü', None])
    def test_unsafe_ids_are_rejected(self, bad_id):
        with pytest.raises(ValueError):
            ledger_key(APPLICATION_DIMENSION, bad_id)
        with pytest.raises(ValueError):
            ledger_key(USECASE_DIMENSION, APP, bad_id)

    def test_application_id_may_not_use_the_reserved_folder(self):
        with pytest.raises(ValueError):
            ledger_key(APPLICATION_DIMENSION, UNASSIGNED_FOLDER)
        with pytest.raises(ValueError):
            ledger_key(USECASE_DIMENSION, '_other', UC)

    def test_usecase_id_may_not_collide_with_application_file(self):
        with pytest.raises(ValueError):
            ledger_key(USECASE_DIMENSION, APP, 'raw')


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


class TestRead:
    def test_missing_object_is_empty(self):
        s3 = _s3_without_object()

        assert read(KEY, s3=s3) == ([], None)
        s3.get_object.assert_called_once_with(Bucket=BUCKET, Key=KEY)

    def test_parses_rows_and_returns_etag(self):
        rows = [_row('2026-11-03'), _row('2026-11-04', cost=2.0)]
        s3 = _s3_with_object(rows, etag='"abc"')

        assert read(KEY, s3=s3) == (rows, '"abc"')

    def test_tolerates_blank_lines_and_missing_trailing_newline(self):
        rows = [_row('2026-11-03'), _row('2026-11-04')]
        body = (rows[0].model_dump_json() + '\n\n' + rows[1].model_dump_json()).encode('utf-8')
        s3 = MagicMock()
        s3.get_object.return_value = _get_object_response(body)

        assert read(KEY, s3=s3)[0] == rows

    def test_skips_and_logs_malformed_lines(self, caplog):
        good = _row('2026-11-04')
        body = b'{"date": "2026-11-03"}\nnot json at all\n' + good.model_dump_json().encode('utf-8') + b'\n'
        s3 = MagicMock()
        s3.get_object.return_value = _get_object_response(body)

        with caplog.at_level(logging.WARNING, logger='cost_ledger'):
            rows, etag = read(KEY, s3=s3)

        assert rows == [good]
        assert etag == '"etag-1"'
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2
        assert all(KEY in w for w in warnings)
        assert any('line 1' in w for w in warnings) and any('line 2' in w for w in warnings)
        assert not any('not json at all' in w for w in warnings)  # line content stays out of the log

    def test_other_client_errors_propagate(self):
        # Deliberate: re-raise AccessDenied. Mapping it to "missing ledger" would hide a
        # broken grant behind an empty result. A missing key reads as NoSuchKey only
        # when the caller has s3:ListBucket on the prefix (lambda-stack.ts grants it to
        # the application router; ownership-check-iam.test.ts pins it).
        s3 = MagicMock()
        s3.get_object.side_effect = _client_error('AccessDenied', 'GetObject')

        with pytest.raises(ClientError):
            read(KEY, s3=s3)

    def test_bucket_falls_back_to_bucket_name(self, monkeypatch):
        monkeypatch.delenv('S3_BUCKET')
        monkeypatch.setenv('BUCKET_NAME', 'router-bucket')
        s3 = _s3_without_object()

        read(KEY, s3=s3)

        s3.get_object.assert_called_once_with(Bucket='router-bucket', Key=KEY)

    def test_no_bucket_configured_fails_closed(self, monkeypatch):
        monkeypatch.delenv('S3_BUCKET')
        s3 = _s3_without_object()

        with pytest.raises(RuntimeError, match='S3_BUCKET'):
            read(KEY, s3=s3)
        s3.get_object.assert_not_called()

    def test_explicit_bucket_wins(self):
        s3 = _s3_without_object()

        read(KEY, s3=s3, bucket='explicit')

        s3.get_object.assert_called_once_with(Bucket='explicit', Key=KEY)

    def test_default_client_is_created_once(self, monkeypatch):
        created = []

        def fake_client(service, **kwargs):
            created.append(service)
            return _s3_without_object()

        monkeypatch.setattr(cost_ledger.boto3, 'client', fake_client)

        read(KEY)
        read(KEY)

        assert created == ['s3']


# ---------------------------------------------------------------------------
# upsert_rows
# ---------------------------------------------------------------------------


def _put_kwargs(s3, index=-1):
    return s3.put_object.call_args_list[index].kwargs


def _rows_in_body(body: bytes):
    return [LedgerRow.model_validate_json(line) for line in body.decode('utf-8').splitlines() if line]


class TestUpsertRows:
    def test_first_write_uses_if_none_match(self):
        s3 = _s3_without_object()
        row = _row('2026-11-04')

        merged = upsert_rows(KEY, [row], s3=s3)

        assert merged == [row]
        kwargs = _put_kwargs(s3)
        assert kwargs['Bucket'] == BUCKET
        assert kwargs['Key'] == KEY
        assert kwargs['IfNoneMatch'] == '*'
        assert 'IfMatch' not in kwargs
        assert kwargs['ContentType'] == LEDGER_CONTENT_TYPE
        assert LEDGER_CONTENT_TYPE == 'application/x-ndjson'
        assert kwargs['Body'] == row.model_dump_json().encode('utf-8') + b'\n'

    def test_existing_file_uses_if_match_with_the_read_etag(self):
        s3 = _s3_with_object([_row('2026-11-03')], etag='"v1"')

        upsert_rows(KEY, [_row('2026-11-04')], s3=s3)

        kwargs = _put_kwargs(s3)
        assert kwargs['IfMatch'] == '"v1"'
        assert 'IfNoneMatch' not in kwargs

    def test_replaces_rows_with_equal_date_and_inserts_the_rest(self):
        existing = [_row('2026-11-02', cost=1.0), _row('2026-11-03', cost=1.0, collected_at='2026-11-04T06:00:00Z')]
        s3 = _s3_with_object(existing)
        replacement = _row('2026-11-03', cost=5.0, collected_at='2026-11-05T06:00:00Z')
        new = _row('2026-11-04', cost=2.0)

        merged = upsert_rows(KEY, [replacement, new], s3=s3)

        assert merged == [existing[0], replacement, new]
        assert _rows_in_body(_put_kwargs(s3)['Body']) == merged

    def test_rows_are_sorted_by_date(self):
        s3 = _s3_with_object([_row('2026-11-04'), _row('2026-11-01')])

        merged = upsert_rows(KEY, [_row('2026-11-03'), _row('2026-11-02')], s3=s3)

        assert [r.date.isoformat() for r in merged] == ['2026-11-01', '2026-11-02', '2026-11-03', '2026-11-04']
        assert _rows_in_body(_put_kwargs(s3)['Body']) == merged

    def test_output_is_byte_identical_between_runs(self):
        rows = [_row('2026-11-03'), _row('2026-11-04')]
        s3_first = _s3_without_object()
        upsert_rows(KEY, list(reversed(rows)), s3=s3_first)
        s3_second = MagicMock()
        s3_second.get_object.return_value = _get_object_response(_put_kwargs(s3_first)['Body'], '"v1"')

        upsert_rows(KEY, rows, s3=s3_second)

        assert _put_kwargs(s3_second)['Body'] == _put_kwargs(s3_first)['Body']

    def test_duplicate_dates_in_new_rows_raise_before_any_s3_call(self):
        s3 = _s3_without_object()

        with pytest.raises(ValueError, match='2026-11-04'):
            upsert_rows(KEY, [_row('2026-11-04'), _row('2026-11-04', cost=2.0)], s3=s3)
        s3.get_object.assert_not_called()
        s3.put_object.assert_not_called()

    def test_no_new_rows_reads_but_does_not_write(self):
        existing = [_row('2026-11-03')]
        s3 = _s3_with_object(existing)

        assert upsert_rows(KEY, [], s3=s3) == existing
        s3.put_object.assert_not_called()

    def test_precondition_failed_rereads_and_retries(self):
        s3 = MagicMock()
        stale = [_row('2026-11-02', cost=1.0)]
        fresh = [_row('2026-11-02', cost=1.0), _row('2026-11-03', cost=3.0)]
        s3.get_object.side_effect = [
            _get_object_response(_body(stale), '"v1"'),
            _get_object_response(_body(fresh), '"v2"'),
        ]
        s3.put_object.side_effect = [_client_error('PreconditionFailed', 'PutObject'), {'ETag': '"v3"'}]
        new = _row('2026-11-04')

        merged = upsert_rows(KEY, [new], s3=s3)

        assert merged == fresh + [new]
        assert s3.get_object.call_count == 2
        assert [c.kwargs['IfMatch'] for c in s3.put_object.call_args_list] == ['"v1"', '"v2"']
        assert _rows_in_body(_put_kwargs(s3)['Body']) == fresh + [new]

    def test_file_created_concurrently_switches_from_if_none_match_to_if_match(self):
        s3 = MagicMock()
        other = _row('2026-11-03')
        s3.get_object.side_effect = [
            _client_error('NoSuchKey', 'GetObject'),
            _get_object_response(_body([other]), '"v1"'),
        ]
        s3.put_object.side_effect = [_client_error('PreconditionFailed', 'PutObject'), {'ETag': '"v2"'}]
        new = _row('2026-11-04')

        assert upsert_rows(KEY, [new], s3=s3) == [other, new]
        first, second = s3.put_object.call_args_list
        assert first.kwargs['IfNoneMatch'] == '*'
        assert second.kwargs['IfMatch'] == '"v1"'

    def test_conditional_request_conflict_is_retried_like_412(self):
        s3 = _s3_with_object([_row('2026-11-03')])
        s3.put_object.side_effect = [_client_error('ConditionalRequestConflict', 'PutObject'), {'ETag': '"v2"'}]

        upsert_rows(KEY, [_row('2026-11-04')], s3=s3)

        assert s3.put_object.call_count == 2

    def test_three_precondition_failures_raise(self, caplog):
        s3 = _s3_with_object([_row('2026-11-03')])
        s3.put_object.side_effect = _client_error('PreconditionFailed', 'PutObject')

        with caplog.at_level(logging.WARNING, logger='cost_ledger'):
            with pytest.raises(ClientError) as excinfo:
                upsert_rows(KEY, [_row('2026-11-04')], s3=s3)

        assert excinfo.value.response['Error']['Code'] == 'PreconditionFailed'
        assert s3.put_object.call_count == MAX_PUT_ATTEMPTS == 3
        assert s3.get_object.call_count == 3
        assert any(KEY in r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)

    def test_other_put_errors_propagate_without_retry(self):
        s3 = _s3_with_object([_row('2026-11-03')])
        s3.put_object.side_effect = _client_error('AccessDenied', 'PutObject')

        with pytest.raises(ClientError):
            upsert_rows(KEY, [_row('2026-11-04')], s3=s3)
        assert s3.put_object.call_count == 1

    def test_malformed_existing_lines_are_dropped_on_rewrite(self):
        good = _row('2026-11-03')
        s3 = MagicMock()
        s3.get_object.return_value = _get_object_response(b'garbage\n' + _body([good]))

        merged = upsert_rows(KEY, [_row('2026-11-04')], s3=s3)

        assert merged[0] == good
        assert b'garbage' not in _put_kwargs(s3)['Body']

    def test_explicit_bucket(self):
        s3 = _s3_without_object()

        upsert_rows(KEY, [_row('2026-11-04')], s3=s3, bucket='explicit')

        assert _put_kwargs(s3)['Bucket'] == 'explicit'
        assert s3.get_object.call_args.kwargs['Bucket'] == 'explicit'


# ---------------------------------------------------------------------------
# read_tail
# ---------------------------------------------------------------------------


class TestReadTail:
    def test_returns_last_n_rows_by_date(self):
        rows = [_row(f'2026-11-{d:02d}') for d in range(1, 8)]
        s3 = _s3_with_object(rows)

        tail = read_tail(KEY, 3, s3=s3)

        assert [r.date.isoformat() for r in tail] == ['2026-11-05', '2026-11-06', '2026-11-07']

    def test_sorts_before_slicing(self):
        s3 = _s3_with_object([_row('2026-11-05'), _row('2026-11-01'), _row('2026-11-03')])

        assert [r.date.isoformat() for r in read_tail(KEY, 2, s3=s3)] == ['2026-11-03', '2026-11-05']

    def test_fewer_rows_than_n_returns_all(self):
        rows = [_row('2026-11-01'), _row('2026-11-02')]
        assert read_tail(KEY, 30, s3=_s3_with_object(rows)) == rows

    def test_missing_file_is_empty(self):
        assert read_tail(KEY, 30, s3=_s3_without_object()) == []

    @pytest.mark.parametrize('n', [0, -1])
    def test_non_positive_n_raises(self, n):
        with pytest.raises(ValueError):
            read_tail(KEY, n, s3=_s3_without_object())


# ---------------------------------------------------------------------------
# Grep guard
# ---------------------------------------------------------------------------


class TestNoInlineLedgerKeys:
    """Grep guard: only cost_ledger.py spells the ``cost_allocation/`` S3 prefix."""

    SKIPPED_DIRS = {'dependencies', '__pycache__', 'node_modules', '.venv'}

    @classmethod
    def _production_modules(cls):
        for root, dirs, files in os.walk(ENDPOINTS_DIR):
            dirs[:] = [d for d in dirs if d not in cls.SKIPPED_DIRS and not d.startswith('.')]
            for name in files:
                if name.endswith('.py') and not name.startswith('test_') and name != 'conftest.py':
                    yield os.path.join(root, name)

    def test_prefix_lives_only_in_cost_ledger(self):
        offenders = []
        for path in self._production_modules():
            if os.path.basename(path) == 'cost_ledger.py':
                continue
            with open(path, encoding='utf-8') as fh:
                if 'cost_allocation/' in fh.read():
                    offenders.append(os.path.relpath(path, ENDPOINTS_DIR))
        assert offenders == [], f'build ledger keys via cost_ledger.ledger_key: {offenders}'

    def test_guard_sees_cost_ledger_itself(self):
        paths = [os.path.basename(p) for p in self._production_modules()]
        assert 'cost_ledger.py' in paths
        assert 'cost_models.py' in paths

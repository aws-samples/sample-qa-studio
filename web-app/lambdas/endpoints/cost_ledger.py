"""Cost allocation: the per-dimension NDJSON ledgers in S3.

Design: ``.kiro/docs/cost-allocation/design.md`` (Data model → S3 ledger).  One
file per dimension under the ``cost_allocation/`` prefix of the artefacts
bucket, one ``LedgerRow`` per line, one line per UTC date, sorted by date:

    cost_allocation/overall.ndjson                        overall
    cost_allocation/{application_id}/raw.ndjson           application
    cost_allocation/{application_id}/{usecase_id}.ndjson  use case, under its application on that date
    cost_allocation/_unassigned/{usecase_id}.ndjson       use case without an application

This module is the only place that spells those keys (``ledger_key``;
``test_cost_ledger.py`` greps every other module for the prefix), and the only
writer: ``upsert_rows`` replaces rows by date and puts the whole file back with
a conditional write (``IfMatch`` on the ETag read, ``IfNoneMatch='*'`` for a
new file), re-reading and retrying on ``412 PreconditionFailed`` so the daily
run and a manual re-run never clobber each other.

The bucket comes from ``S3_BUCKET`` (worker stack: the collector) or
``BUCKET_NAME`` (lambda stack: the API routes); callers may pass ``bucket=``
explicitly.  No raw API responses are stored here (design decision 4b).

Imports pydantic through ``cost_models``: Lambda entry modules must
``import lambda_init`` first.
"""
import logging
import os
import re
from typing import Iterable, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from cost_models import LedgerRow

logger = logging.getLogger(__name__)

LEDGER_PREFIX = 'cost_allocation/'
LEDGER_SUFFIX = '.ndjson'
LEDGER_CONTENT_TYPE = 'application/x-ndjson'

OVERALL_DIMENSION = 'overall'
APPLICATION_DIMENSION = 'application'
USECASE_DIMENSION = 'usecase'

#: Folder of use cases without an ``application_id``; the underscore cannot start a UUID.
UNASSIGNED_FOLDER = '_unassigned'
#: File name of the application's own ledger inside its folder.
APPLICATION_FILE = 'raw'

#: Attempts of read → merge → conditional put before a conflict is raised.
MAX_PUT_ATTEMPTS = 3

#: Error codes S3 returns when the conditional put lost a race; both are retried.
_RETRYABLE_PUT_ERRORS = ('PreconditionFailed', 'ConditionalRequestConflict')

_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')

_s3_client = None


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


def ledger_key(dimension: str, *ids: Optional[str]) -> str:
    """The S3 key of a dimension's ledger.

    ``ledger_key('overall')``,
    ``ledger_key('application', application_id)``,
    ``ledger_key('usecase', application_id_or_None, usecase_id)`` — the
    application is the one the use case belonged to on the row's date, so a
    reassigned use case starts a new file; ``None``/``''`` files it under
    ``_unassigned/``.  Raises ``ValueError`` on an unknown dimension, wrong
    arity or an id that is not safe in a key.
    """
    if dimension == OVERALL_DIMENSION:
        _expect_ids(dimension, ids, 0)
        return f'{LEDGER_PREFIX}{OVERALL_DIMENSION}{LEDGER_SUFFIX}'
    if dimension == APPLICATION_DIMENSION:
        _expect_ids(dimension, ids, 1)
        return f'{LEDGER_PREFIX}{_application_folder(ids[0])}/{APPLICATION_FILE}{LEDGER_SUFFIX}'
    if dimension == USECASE_DIMENSION:
        _expect_ids(dimension, ids, 2)
        application_id, usecase_id = ids
        folder = _application_folder(application_id) if application_id else UNASSIGNED_FOLDER
        usecase_id = _safe_id('usecase_id', usecase_id)
        if usecase_id == APPLICATION_FILE:
            raise ValueError(f'usecase_id {usecase_id!r} collides with the application ledger file')
        return f'{LEDGER_PREFIX}{folder}/{usecase_id}{LEDGER_SUFFIX}'
    raise ValueError(f'unknown ledger dimension {dimension!r}')


def _expect_ids(dimension: str, ids: tuple, count: int) -> None:
    if len(ids) != count:
        raise ValueError(f'ledger_key({dimension!r}) takes {count} id(s), got {len(ids)}')


def _application_folder(application_id: Optional[str]) -> str:
    return _safe_id('application_id', application_id)


def _safe_id(name: str, value: Optional[str]) -> str:
    """An id that is one path segment: no slashes, dots, spaces or leading underscore (reserved)."""
    if not isinstance(value, str) or not _ID_PATTERN.match(value):
        raise ValueError(f'{name} {value!r} is not a safe ledger path segment')
    return value


# ---------------------------------------------------------------------------
# Bucket / client
# ---------------------------------------------------------------------------


def get_s3_client():
    """The module's S3 client, created on first use."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client('s3')
    return _s3_client


def get_ledger_bucket() -> str:
    """The artefacts bucket: ``S3_BUCKET`` (worker stack) or ``BUCKET_NAME`` (lambda stack)."""
    bucket = os.environ.get('S3_BUCKET') or os.environ.get('BUCKET_NAME')
    if not bucket:
        # Fail closed: never fall back to a guessable bucket name (bucket squatting).
        raise RuntimeError("neither 'S3_BUCKET' nor 'BUCKET_NAME' is set")
    return bucket


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def read(key: str, *, s3=None, bucket: Optional[str] = None) -> Tuple[List[LedgerRow], Optional[str]]:
    """The rows of a ledger in file order and the object's ETag.

    A missing object is ``([], None)``.  A line that is not a valid
    ``LedgerRow`` is skipped with a warning (line number, not content) so one
    bad line never hides the rest of the dimension's history.
    """
    s3 = s3 or get_s3_client()
    bucket = bucket or get_ledger_bucket()
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'NoSuchKey':
            return [], None
        raise
    body = response['Body'].read()
    return _parse_rows(key, body), response.get('ETag')


def read_tail(key: str, n: int, *, s3=None, bucket: Optional[str] = None) -> List[LedgerRow]:
    """The last ``n`` rows by date (fewer when the ledger is shorter; ``[]`` for a missing file)."""
    if n <= 0:
        raise ValueError(f'read_tail needs n ≥ 1, got {n}')
    rows, _ = read(key, s3=s3, bucket=bucket)
    return _sorted(rows)[-n:]


def _parse_rows(key: str, body: bytes) -> List[LedgerRow]:
    rows: List[LedgerRow] = []
    for line_no, line in enumerate(body.decode('utf-8').splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(LedgerRow.model_validate_json(line))
        except ValueError as e:  # pydantic.ValidationError is a ValueError
            logger.warning('Skipping malformed ledger line %d of %s (%s)', line_no, key, type(e).__name__)
    return rows


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def upsert_rows(key: str, new_rows: Iterable[LedgerRow], *, s3=None,
                bucket: Optional[str] = None) -> List[LedgerRow]:
    """Replace the ledger's rows with the same ``date`` as ``new_rows``, insert the rest, write back.

    Read → merge → sort by date → ``put_object`` with ``IfMatch=<etag read>``
    (``IfNoneMatch='*'`` when the file did not exist).  A ``412
    PreconditionFailed`` (or ``409 ConditionalRequestConflict``) means another
    writer won the race: re-read and retry, ``MAX_PUT_ATTEMPTS`` times, then
    the last ``ClientError`` is raised.  Returns the full merged, sorted row
    list after the successful put so the caller can ``summarize`` without a
    second read.  With no ``new_rows`` the ledger is read but not written.
    Raises ``ValueError`` when ``new_rows`` repeat a date.
    """
    new_rows = list(new_rows)
    _assert_unique_dates(new_rows)
    s3 = s3 or get_s3_client()
    bucket = bucket or get_ledger_bucket()
    for attempt in range(1, MAX_PUT_ATTEMPTS + 1):
        existing, etag = read(key, s3=s3, bucket=bucket)
        if not new_rows:
            return _sorted(existing)
        merged = _merge(existing, new_rows)
        condition = {'IfMatch': etag} if etag else {'IfNoneMatch': '*'}
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=_serialize(merged), ContentType=LEDGER_CONTENT_TYPE,
                          **condition)
            return merged
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code')
            if code not in _RETRYABLE_PUT_ERRORS:
                raise
            if attempt == MAX_PUT_ATTEMPTS:
                logger.error('Giving up on %s after %d conditional put attempts (%s)', key, attempt, code)
                raise
            logger.warning('Conditional put of %s lost a race (%s, attempt %d/%d)', key, code, attempt,
                           MAX_PUT_ATTEMPTS)
    raise RuntimeError('unreachable: MAX_PUT_ATTEMPTS must be ≥ 1')


def _assert_unique_dates(rows: List[LedgerRow]) -> None:
    seen = set()
    for row in rows:
        if row.date in seen:
            raise ValueError(f'new_rows contain {row.date.isoformat()} more than once')
        seen.add(row.date)


def _merge(existing: List[LedgerRow], new_rows: List[LedgerRow]) -> List[LedgerRow]:
    by_date = {row.date: row for row in existing}
    for row in new_rows:
        by_date[row.date] = row
    return _sorted(by_date.values())


def _sorted(rows: Iterable[LedgerRow]) -> List[LedgerRow]:
    return sorted(rows, key=lambda row: row.date)


def _serialize(rows: List[LedgerRow]) -> bytes:
    return ''.join(row.model_dump_json() + '\n' for row in rows).encode('utf-8')

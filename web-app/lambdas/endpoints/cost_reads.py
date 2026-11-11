"""Cost allocation: the read side shared by the cost API handlers.

Design: ``.kiro/docs/cost-allocation/design.md`` (Serving / API).  The three
routes (``/applications/{id}/costs``, ``/usecase/{id}/costs``,
``/dashboard/costs``) only read what the collector wrote:

* the ``USAGE#… / SUMMARY`` items — one ``GetItem`` per dimension, or one
  chunked ``BatchGetItem`` for a list of dimensions (``batch_get_summaries``);
* the last ``DAYS_IN_SERIES`` rows of a dimension's S3 ledger
  (``ledger_days``, through ``cost_ledger.read_tail``).

No allocation logic lives here.  Imports pydantic through ``cost_models``:
Lambda entry modules must ``import lambda_init`` first.
"""
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional

import cost_ledger
from cost_models import SUMMARY_SK, CostSummary
from utils import get_table_name

logger = logging.getLogger(__name__)

#: Ledger rows the ``days`` series carries (the 30-day window of the UI).
DAYS_IN_SERIES = 30

#: DynamoDB ``BatchGetItem`` accepts at most 100 keys per call.
BATCH_GET_MAX_KEYS = 100
#: Retries of ``UnprocessedKeys`` before the read is given up.
BATCH_GET_MAX_ATTEMPTS = 3

SummaryBody = Optional[Dict[str, Any]]


def summary_body(item: Optional[Mapping[str, Any]]) -> SummaryBody:
    """The API ``summary`` object of a SUMMARY item (``pk``/``sk`` dropped); ``None`` for a missing item."""
    if not item:
        return None
    return CostSummary.from_item(item).model_dump(mode='json')


def get_summary(table, dimension_key: str) -> SummaryBody:
    """One dimension's summary via ``GetItem``."""
    response = table.get_item(Key={'pk': dimension_key, 'sk': SUMMARY_SK})
    return summary_body(response.get('Item'))


def batch_get_summaries(dynamodb, dimension_keys: Iterable[str]) -> Dict[str, SummaryBody]:
    """``dimension_key → summary`` (``None`` when the item is missing) for many dimensions in one pass."""
    keys = list(dict.fromkeys(dimension_keys))
    items = batch_get(dynamodb, [{'pk': key, 'sk': SUMMARY_SK} for key in keys])
    by_pk = {item['pk']: item for item in items}
    return {key: summary_body(by_pk.get(key)) for key in keys}


def batch_get(dynamodb, keys: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """``BatchGetItem`` on the table for ``keys`` in chunks of ``BATCH_GET_MAX_KEYS``.

    Retries ``UnprocessedKeys`` up to ``BATCH_GET_MAX_ATTEMPTS`` times per chunk and
    raises ``RuntimeError`` when keys are still unprocessed (the caller answers 500
    rather than returning a partial list that looks complete).  Items come back in
    no particular order; missing keys are simply absent.
    """
    if not keys:
        return []
    table_name = get_table_name()
    items: List[Dict[str, Any]] = []
    for start in range(0, len(keys), BATCH_GET_MAX_KEYS):
        request_items = {table_name: {'Keys': keys[start:start + BATCH_GET_MAX_KEYS]}}
        for _ in range(BATCH_GET_MAX_ATTEMPTS):
            response = dynamodb.batch_get_item(RequestItems=request_items)
            items.extend(response.get('Responses', {}).get(table_name, []))
            request_items = response.get('UnprocessedKeys') or {}
            if not request_items:
                break
        if request_items:
            raise RuntimeError('batch_get: keys left unprocessed after retries')
    return items


def ledger_days(key: str) -> List[Dict[str, Any]]:
    """The last ``DAYS_IN_SERIES`` rows of the ledger at ``key`` as API objects (``[]`` for a missing file)."""
    return [row.model_dump(mode='json') for row in cost_ledger.read_tail(key, DAYS_IN_SERIES)]


def window_30d(summary: SummaryBody) -> float:
    """Sort key for cost rows: 30-day cost, with a missing summary sorting after every real one."""
    if summary is None:
        return float('-inf')
    return float(summary.get('window_30d') or 0.0)

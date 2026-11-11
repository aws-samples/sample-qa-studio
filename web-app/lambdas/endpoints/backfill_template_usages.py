"""One-off, deploy-time backfill of ``TEMPLATE#{tid} / USAGE#{usecase_id}`` records.

Use-case steps linked to a template before usage tracking existed have no
USAGE record, so ``delete_template`` could not find them.  A CDK ``Trigger``
invokes this handler during ``cdk deploy`` (re-run only when this file
changes).  It scans the table for ``USECASE#* / STEP#*`` items that carry
``template_id`` and writes one idempotent USAGE record per distinct
``(template_id, usecase_id)`` pair.

This is deliberately the **only scan** in the template feature and it is
not on any request path — do not copy it into an API handler.  When the
remaining execution time drops below ``HANDOVER_MS`` and the scan is not
finished, the handler invokes itself asynchronously with the
``ExclusiveStartKey`` and returns, so a large table never fails the deploy.
Per-item write errors are logged and counted, never raised: a failing
Trigger fails the whole deploy.
"""
import json
import logging
import os
from typing import Any, Dict, Optional, Set, Tuple

import boto3

from template_usage import record_usage
from utils import get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#: Hand over to a fresh invocation when less than this is left.
HANDOVER_MS = 60_000

_SCAN_KWARGS: Dict[str, Any] = {
    'ProjectionExpression': 'pk, sk, template_id',
    'FilterExpression': 'begins_with(pk, :uc) AND begins_with(sk, :st) AND attribute_exists(template_id)',
    'ExpressionAttributeValues': {':uc': 'USECASE#', ':st': 'STEP#'},
}


def _pair_of(item: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    template_id = item.get('template_id')
    if not template_id:
        return None
    usecase_id = str(item.get('pk', ''))[len('USECASE#'):]
    return (str(template_id), usecase_id) if usecase_id else None


def _continue_later(context: Any, start_key: Dict[str, Any]) -> None:
    function_name = getattr(context, 'function_name', None) or os.environ.get('AWS_LAMBDA_FUNCTION_NAME', '')
    boto3.client('lambda').invoke(
        FunctionName=function_name,
        InvocationType='Event',
        Payload=json.dumps({'ExclusiveStartKey': start_key}),
    )


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    start_key = (event or {}).get('ExclusiveStartKey')
    seen: Set[Tuple[str, str]] = set()
    pages_scanned = written = failed = 0
    continued = False

    while True:
        kwargs = dict(_SCAN_KWARGS)
        if start_key:
            kwargs['ExclusiveStartKey'] = start_key
        response = table.scan(**kwargs)
        pages_scanned += 1

        for item in response.get('Items', []):
            pair = _pair_of(item)
            if pair is None or pair in seen:
                continue
            seen.add(pair)
            try:
                record_usage(table, *pair)
                written += 1
            except Exception as e:  # noqa: BLE001 — a failing Trigger fails the deploy
                failed += 1
                logger.warning(f"backfill: could not write usage for template {pair[0]} / use case {pair[1]}: {e}")

        start_key = response.get('LastEvaluatedKey')
        if not start_key:
            break
        if context.get_remaining_time_in_millis() < HANDOVER_MS:
            _continue_later(context, start_key)
            continued = True
            break

    summary = {'pages_scanned': pages_scanned, 'pairs_written': written, 'pairs_failed': failed, 'continued': continued}
    logger.info(f"backfill_template_usages: {json.dumps(summary)}")
    return summary

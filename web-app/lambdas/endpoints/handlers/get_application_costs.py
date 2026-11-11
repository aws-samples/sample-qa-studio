import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key

import cost_reads
from cost_ledger import APPLICATION_DIMENSION, ledger_key
from cost_models import SUMMARY_SK, application_dimension_key, usecase_dimension_key
from resource_auth import app_from_path, require_resource_access
from utils import create_response, get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', app_from_path, scopes=['api/applications.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /applications/{id}/costs — ``{summary, days, usecases}``.

    ``summary`` is the application's ``USAGE#APPLICATION#{id} / SUMMARY`` item
    (``null`` until the collector has run), ``days`` the last 30 rows of its S3
    ledger (``[]`` without a file) and ``usecases`` one row per associated use
    case — ``{usecase_id, name, summary}`` — sorted by 30-day cost, highest first,
    use cases without a summary last.
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        return create_response(200, {
            'summary': cost_reads.get_summary(table, application_dimension_key(app_id)),
            'days': cost_reads.ledger_days(ledger_key(APPLICATION_DIMENSION, app_id)),
            'usecases': _usecase_rows(dynamodb, table, app_id),
        })
    except Exception as e:
        logger.error(f"Error fetching costs for application {app_id}: {e}", exc_info=True)
        return create_response(500, {'error': f'Failed to fetch application costs: {str(e)}'})


def _usecase_rows(dynamodb, table, app_id: str) -> List[Dict[str, Any]]:
    """One row per ``APPLICATION#{id} / USECASE#…`` association, names and summaries from one batch read."""
    associations = table.query(
        KeyConditionExpression=Key('pk').eq(f'APPLICATION#{app_id}') & Key('sk').begins_with('USECASE#')
    ).get('Items', [])
    usecase_ids = [item['sk'].split('#', 1)[1] for item in associations]
    if not usecase_ids:
        return []

    keys = [{'pk': 'USECASES', 'sk': f'USECASE#{uid}'} for uid in usecase_ids]
    keys += [{'pk': usecase_dimension_key(uid), 'sk': SUMMARY_SK} for uid in usecase_ids]
    names: Dict[str, str] = {}
    summaries: Dict[str, Dict[str, Any]] = {}
    for item in cost_reads.batch_get(dynamodb, keys):
        if item['pk'] == 'USECASES':
            names[item['sk'].split('#', 1)[1]] = item.get('name', '')
        else:
            summaries[item['pk']] = item

    rows = [{
        'usecase_id': uid,
        'name': names.get(uid, ''),
        'summary': cost_reads.summary_body(summaries.get(usecase_dimension_key(uid))),
    } for uid in usecase_ids]
    rows.sort(key=lambda row: (-cost_reads.window_30d(row['summary']), row['name'].lower(), row['usecase_id']))
    return rows

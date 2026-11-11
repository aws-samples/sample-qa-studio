import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key

import cost_reads
from cost_models import OVERALL_DIMENSION_KEY, application_dimension_key
from resource_auth import filter_visible_apps, is_studio_admin
from utils import create_response, get_table_name, require_scopes

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /dashboard/costs — ``{overall, applications}``.

    ``applications`` is one ``{application_id, summary}`` row per application the
    caller may view (the same ``filter_visible_apps`` rule as
    ``/dashboard/overview``), sorted by 30-day cost, highest first.  ``overall``
    is the studio-wide ``USAGE#OVERALL / SUMMARY`` for studio admins only; every
    other caller gets ``null`` (design: Open Question 2, answered conservatively —
    no bucket rows).  Reads SUMMARY items only, never a ledger.
    """
    identity, error_response = require_scopes(event, ['api/applications.read'])
    if error_response:
        return error_response

    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        app_ids = _visible_application_ids(dynamodb, table, identity)
        summaries = cost_reads.batch_get_summaries(dynamodb, [application_dimension_key(a) for a in app_ids])
        rows = [{'application_id': app_id, 'summary': summaries[application_dimension_key(app_id)]}
                for app_id in app_ids]
        rows.sort(key=lambda row: (-cost_reads.window_30d(row['summary']), row['application_id']))

        overall = cost_reads.get_summary(table, OVERALL_DIMENSION_KEY) if is_studio_admin(identity) else None
        return create_response(200, {'overall': overall, 'applications': rows})
    except Exception as e:
        logger.error(f"Error fetching dashboard costs: {e}", exc_info=True)
        return create_response(500, {'error': f'Failed to fetch dashboard costs: {str(e)}'})


def _visible_application_ids(dynamodb, table, identity: dict) -> List[str]:
    """Ids of the applications the caller may view: APPLICATIONS index → metadata → ``filter_visible_apps``."""
    index_response = table.query(
        KeyConditionExpression=Key('pk').eq('APPLICATIONS') & Key('sk').begins_with('APPLICATION#')
    )
    app_ids = [item['id'] for item in index_response.get('Items', [])]
    if not app_ids:
        return []
    keys = [{'pk': f'APPLICATION#{aid}', 'sk': 'METADATA'} for aid in app_ids]
    apps = cost_reads.batch_get(dynamodb, keys)
    return [app['id'] for app in filter_visible_apps(identity, apps)]

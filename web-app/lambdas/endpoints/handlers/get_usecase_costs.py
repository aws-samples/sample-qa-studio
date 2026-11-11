import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict

import boto3

import cost_reads
from cost_ledger import USECASE_DIMENSION, ledger_key
from cost_models import usecase_dimension_key
import permissions_repo
from resource_auth import require_resource_access, usecase_from_path
from utils import create_response, get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', usecase_from_path, scopes=['api/usecases.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /usecase/{id}/costs — ``{summary, days}``.

    ``summary`` is the ``USAGE#USECASE#{id} / SUMMARY`` item (``null`` until the
    collector has run).  ``days`` is the last 30 rows of the use case's
    **current** ledger file — the one under the application it belongs to now
    (``_unassigned/`` without one).  Files left under a previous application are
    history only and are not read (design: Data model → S3 ledger).
    """
    usecase_id = event['pathParameters']['id']  # validated by usecase_from_path
    try:
        # The guard has just resolved the owner; the same projected read gives the
        # current application_id (None for an orphan, which only admins reach).
        owner = permissions_repo.get_usecase_owner(usecase_id) or {}
        application_id = owner.get('application_id') or None

        table = boto3.resource('dynamodb').Table(get_table_name())
        return create_response(200, {
            'summary': cost_reads.get_summary(table, usecase_dimension_key(usecase_id)),
            'days': cost_reads.ledger_days(ledger_key(USECASE_DIMENSION, application_id, usecase_id)),
        })
    except Exception as e:
        logger.error(f"Error fetching costs for use case {usecase_id}: {e}", exc_info=True)
        return create_response(500, {'error': f'Failed to fetch use case costs: {str(e)}'})

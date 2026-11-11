"""``GET /templates/{id}/usages`` — the use cases that have steps linked to a template.

Backed by the ``USAGE#`` records in the template partition
(``template_usage``).  A record whose use case no longer exists is skipped
and logged — a GET never repairs data.  Used by the CLI delete prompt,
``templates get`` and the web UI delete modal.
"""
import logging
from typing import Any, Dict, List

import boto3

from template_store import get_template_metadata
from template_usage import list_usages
from utils import create_response, get_table_name, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        user_identity, error = require_scopes(event, ['api/templates.read'])
        if error:
            return error

        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'template ID')
        if error:
            return error

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        if get_template_metadata(table, template_id) is None:
            return create_response(404, {'error': 'Template not found'})

        usages: List[Dict[str, str]] = []
        for usage in list_usages(table, template_id):
            usecase_id = usage['usecase_id']
            usecase = table.get_item(Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'}).get('Item')
            if usecase is None:
                logger.info(f"Template {template_id}: stale usage record for use case {usecase_id}; skipped")
                continue
            usages.append({'usecase_id': usecase_id, 'name': usecase.get('name', '')})
        usages.sort(key=lambda u: u['name'])

        return create_response(200, {'usages': usages, 'count': len(usages)})

    except Exception as e:
        logger.error(f"Error listing template usages: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

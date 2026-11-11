import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Key

from resource_auth import require_resource_access, usecase_from_path
from template_expansion import (
    build_linked_steps,
    load_template_bundle,
    merge_variables,
    splice_and_renumber,
    template_secret_keys,
)
from template_usage import record_usage
from utils import create_response, get_current_timestamp, get_table_name

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#: ``insert_position`` sentinel for "append".
APPEND = -1


def resolve_insert_position(raw: Any, existing_count: int) -> Tuple[Optional[int], Optional[str]]:
    """Apply the ``insert_position`` contract; return ``(position, error_message)``.

    omitted / ``-1`` → append; ``0`` → ``1`` (older UI builds send 0 for
    "at the beginning"); ``1..n+1`` → the template's first step becomes
    step N; anything else is an error.
    """
    if raw is None or raw == APPEND:
        return existing_count + 1, None
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None, 'insert_position must be an integer'
    if raw == 0:
        return 1, None
    if 1 <= raw <= existing_count + 1:
        return raw, None
    return None, f'insert_position must be between 1 and {existing_count + 1} (or -1 to append)'


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write', 'api/templates.read'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to import template steps into a usecase.

    Args:
        event: API Gateway proxy request event
        context: Lambda context

    Returns:
        API Gateway proxy response with import confirmation
    """
    try:
        # Get usecase ID from path
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})

        template_id = body.get('template_id', '')
        if not template_id:
            return create_response(400, {'error': 'template_id is required'})

        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        bundle = load_template_bundle(table, template_id)
        if bundle is None:
            return create_response(404, {'error': 'Template not found'})

        existing_steps: List[Dict[str, Any]] = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#')
        ).get('Items', [])
        existing_steps.sort(key=lambda s: int(s.get('sort', 0)))

        position, position_error = resolve_insert_position(body.get('insert_position'), len(existing_steps))
        if position_error:
            return create_response(400, {'error': position_error})

        now = get_current_timestamp()
        new_steps = build_linked_steps(bundle, usecase_id, position, now)
        renumbered = splice_and_renumber(existing_steps, new_steps, position)
        logger.info(
            f"Inserting {len(new_steps)} template steps at position {position}; "
            f"renumbering {len(renumbered)} existing steps"
        )

        # Sort values are final before any write, so a batch is safe.
        with table.batch_writer() as batch:
            for step in new_steps + renumbered:
                batch.put_item(Item=step)

        # Reverse index for delete_template; idempotent on re-insert.
        record_usage(table, template_id, usecase_id)

        if bundle.variables:
            usecase_vars = table.get_item(
                Key={'pk': f'USECASE#{usecase_id}', 'sk': 'USECASE_VARIABLES'}
            ).get('Item') or {
                'pk': f'USECASE#{usecase_id}',
                'sk': 'USECASE_VARIABLES',
                'variables': [],
                'created_at': now,
            }
            usecase_vars['variables'] = merge_variables(usecase_vars.get('variables', []), bundle.variables)
            table.put_item(Item=usecase_vars)

        # Secret steps need values before the first run; the caller collects
        # them and stores them via POST /usecase/{id}/secrets.
        missing_secrets = template_secret_keys(bundle)

        response_data: Dict[str, Any] = {
            'message': 'Template imported successfully',
            'steps_created': len(new_steps),
        }
        if missing_secrets:
            response_data['missingSecrets'] = missing_secrets
        return create_response(201, response_data)

    except Exception as e:
        logger.error(f"Error importing template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

"""``DELETE /templates/{id}`` — unlink use-case steps, then remove the template; ``204``.

Use cases that inserted the template keep their steps as they are; only the
template linkage (``template_id`` / ``template_step_id`` /
``template_version``) is removed so they become plain steps.  The linked
use cases are found through the ``USAGE#`` records in the template's
partition (``template_usage``).

Order: unlink first, delete last.  If the Lambda dies halfway the template
still exists and a retry redoes the idempotent unlink; the reverse order
would leave dangling links nothing can find.

The unlink is a system side effect of deleting a shared resource and runs
under ``api/templates.write`` without per-use-case authorization (the step
definitions are not changed, only the dangling pointer is dropped).
"""
import logging
from typing import Any, Dict

import boto3
from boto3.dynamodb.conditions import Key

from template_store import TEMPLATES_PK, get_template_metadata, template_sk
from template_usage import list_usages, unlink_usecase_steps
from utils import create_response, get_table_name, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        user_identity, error = require_scopes(event, ['api/templates.write'])
        if error:
            return error

        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'template ID')
        if error:
            return error

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        if get_template_metadata(table, template_id) is None:
            return create_response(404, {'error': 'Template not found'})

        # 1. Turn every linked use-case step into a plain step.
        usages = list_usages(table, template_id)
        unlinked = 0
        for usage in usages:
            unlinked += unlink_usecase_steps(table, template_id, usage['usecase_id'])
        logger.info(f"Template {template_id}: unlinked {unlinked} steps across {len(usages)} use cases")

        # 2. Wipe the partition: steps, variables, usages.
        partition_items = table.query(KeyConditionExpression=Key('pk').eq(f'TEMPLATE#{template_id}')).get('Items', [])
        with table.batch_writer() as batch:
            for item in partition_items:
                batch.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

        # 3. Metadata last: while it exists the template is still deletable on retry.
        table.delete_item(Key={'pk': TEMPLATES_PK, 'sk': template_sk(template_id)})

        return create_response(204, None)

    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

"""``PUT /templates/{id}`` — replace a template's definition atomically.

The body is the template file format (``template_definition``) where steps
may carry the ``id`` of an existing template step:

| step in file          | existing step | action                                    |
|-----------------------|---------------|-------------------------------------------|
| has ``id``, matches   | yes           | Put whole item (``id``, ``created_at`` kept) |
| has ``id``, no match  | —             | ``400``, nothing written                  |
| no ``id``             | —             | Put with a fresh uuid                     |
| —                     | not in file   | Delete                                    |

Matching by ``id`` keeps ``template_step_id`` on linked use-case steps
valid; matching by position would relink every step after an insertion.
Whole-item Puts mean a field removed from the file disappears.  Metadata
(``name`` … ``tags``, ``updated_at``) and the **single** ``version`` bump
are one ``Update``; variables are a Put (non-empty) or Delete (empty).
Everything is one ``transact_write_items`` (max 100 items → at most
``MAX_STEPS`` steps).

Use-case steps linked to a template step that was deleted keep their
``template_step_id`` (same as the UI's delete-step today); readers tolerate
that.
"""
import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from pydantic import ValidationError

from step_copy import copy_step_fields
from template_definition import (
    TemplateDefinitionRequest,
    placeholder_in_steps,
    step_rule_error,
    validation_message,
)
from template_expansion import NESTED_TEMPLATE_ERROR
from template_store import TEMPLATES_PK, get_template_metadata, template_sk
from utils import create_response, get_current_timestamp, get_table_name, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#: DynamoDB transaction limit.
TRANSACT_MAX_ITEMS = 100
#: One metadata Update and one VARIABLES Put/Delete always ride along.
MAX_STEPS = TRANSACT_MAX_ITEMS - 2

_serializer = TypeSerializer()


def _typed(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _serializer.serialize(value) for key, value in item.items()}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        user_identity, error = require_scopes(event, ['api/templates.write'])
        if error:
            return error

        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'template ID')
        if error:
            return error

        try:
            body = json.loads(event.get('body') or '{}')
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})

        if placeholder_in_steps(body.get('steps') if isinstance(body, dict) else None):
            return create_response(400, {'error': NESTED_TEMPLATE_ERROR, 'message': NESTED_TEMPLATE_ERROR})

        try:
            request = TemplateDefinitionRequest.model_validate(body)
        except ValidationError as e:
            return create_response(400, {'error': 'Invalid template file', 'message': validation_message(e)})

        rule_error = step_rule_error(request.steps)
        if rule_error:
            return create_response(400, {'error': rule_error, 'message': rule_error})

        if len(request.steps) > MAX_STEPS:
            message = f'template too large for an atomic update (max {MAX_STEPS} steps)'
            return create_response(400, {'error': message, 'message': message})

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        metadata = get_template_metadata(table, template_id)
        if metadata is None:
            return create_response(404, {'error': 'Template not found'})

        existing_steps = table.query(
            KeyConditionExpression=Key('pk').eq(f'TEMPLATE#{template_id}') & Key('sk').begins_with('STEP#')
        ).get('Items', [])
        existing_by_id = {str(step.get('id')): step for step in existing_steps}

        # Every file id must belong to this template — checked before any write.
        for position, step in enumerate(request.steps):
            if step.id is not None and step.id not in existing_by_id:
                message = f'steps[{position}]: id {step.id} does not belong to template {template_id}'
                return create_response(400, {'error': message, 'message': message})

        now = get_current_timestamp()
        table_name = get_table_name()
        transact_items: List[Dict[str, Any]] = []
        created = updated = 0

        for position, step in enumerate(sorted(request.steps, key=lambda s: s.sort), start=1):
            if step.id is None:
                step_id = str(uuid4())
                created_at = now
                created += 1
            else:
                step_id = step.id
                created_at = existing_by_id[step_id].get('created_at', now)
                updated += 1
            item = {
                'pk': f'TEMPLATE#{template_id}',
                'sk': f'STEP#{step_id}',
                'id': step_id,
                'sort': position,
                'created_at': created_at,
                **copy_step_fields(step.model_dump()),
            }
            transact_items.append({'Put': {'TableName': table_name, 'Item': _typed(item)}})

        file_ids = {step.id for step in request.steps if step.id is not None}
        deleted_ids = sorted(set(existing_by_id) - file_ids)
        for step_id in deleted_ids:
            transact_items.append({'Delete': {
                'TableName': table_name,
                'Key': _typed({'pk': f'TEMPLATE#{template_id}', 'sk': f'STEP#{step_id}'}),
            }})

        # Metadata + the one version bump.
        transact_items.append({'Update': {
            'TableName': table_name,
            'Key': _typed({'pk': TEMPLATES_PK, 'sk': template_sk(template_id)}),
            'UpdateExpression': (
                'SET #name = :name, #desc = :desc, category = :category, tags = :tags, updated_at = :updated_at '
                'ADD #version :one'
            ),
            'ConditionExpression': 'attribute_exists(pk)',
            'ExpressionAttributeNames': {'#name': 'name', '#desc': 'description', '#version': 'version'},
            'ExpressionAttributeValues': _typed({
                ':name': request.template.name,
                ':desc': request.template.description,
                ':category': request.template.category,
                ':tags': request.template.tags,
                ':updated_at': now,
                ':one': 1,
            }),
        }})

        variables_key = {'pk': f'TEMPLATE#{template_id}', 'sk': 'VARIABLES'}
        if request.variables:
            transact_items.append({'Put': {'TableName': table_name, 'Item': _typed({
                **variables_key,
                'variables': [v.model_dump() for v in request.variables],
                'created_at': now,
            })}})
        else:
            transact_items.append({'Delete': {'TableName': table_name, 'Key': _typed(variables_key)}})

        boto3.client('dynamodb').transact_write_items(TransactItems=transact_items)

        new_version = int(metadata.get('version', 0)) + 1
        logger.info(
            f"Replaced template {template_id}: {updated} updated, {created} created, {len(deleted_ids)} deleted; "
            f"version {new_version}"
        )
        return create_response(200, {
            'id': template_id,
            'name': request.template.name,
            'version': new_version,
            'stepsCreated': created,
            'stepsUpdated': updated,
            'stepsDeleted': len(deleted_ids),
        })

    except Exception as e:
        logger.error(f"Error replacing template definition: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

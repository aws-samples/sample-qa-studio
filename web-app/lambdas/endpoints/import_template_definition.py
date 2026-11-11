"""``POST /templates/import`` — create a template from a template file in one call.

The CLI's ``qa-studio templates create <file>`` posts the template-file
format here.  Metadata (``version: 1``), steps and variables are written
together so a failed run never leaves a half-built template behind (the
alternative — ``POST /templates`` + N × ``/steps`` + ``/variables`` — can).

Step ``id``s in the file are ignored: a new template always gets fresh step
ids (``PUT /templates/{id}`` is the endpoint that honours them).
"""
import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

import boto3
from pydantic import ValidationError

from step_copy import copy_step_fields
from template_definition import (
    TemplateDefinitionRequest,
    placeholder_in_steps,
    step_rule_error,
    validation_message,
)
from template_expansion import NESTED_TEMPLATE_ERROR
from template_store import TEMPLATES_PK, template_sk
from utils import create_response, get_current_timestamp, get_table_name, require_scopes

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        user_identity, error = require_scopes(event, ['api/templates.write'])
        if error:
            return error
        email = user_identity.get('email') or user_identity.get('identity', 'unknown')

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

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        template_id = str(uuid4())
        now = get_current_timestamp()
        metadata = {
            'pk': TEMPLATES_PK,
            'sk': template_sk(template_id),
            'id': template_id,
            'name': request.template.name,
            'description': request.template.description,
            'category': request.template.category,
            'tags': request.template.tags,
            'created_by': email,
            'created_at': now,
            'updated_at': now,
            'version': 1,
        }

        step_items: List[Dict[str, Any]] = []
        for position, step in enumerate(sorted(request.steps, key=lambda s: s.sort), start=1):
            step_id = str(uuid4())
            step_items.append({
                'pk': f'TEMPLATE#{template_id}',
                'sk': f'STEP#{step_id}',
                'id': step_id,
                'sort': position,
                'created_at': now,
                **copy_step_fields(step.model_dump()),
            })

        with table.batch_writer() as batch:
            batch.put_item(Item=metadata)
            for item in step_items:
                batch.put_item(Item=item)
            if request.variables:
                batch.put_item(Item={
                    'pk': f'TEMPLATE#{template_id}',
                    'sk': 'VARIABLES',
                    'variables': [v.model_dump() for v in request.variables],
                    'created_at': now,
                })

        logger.info(f"Imported template {template_id} with {len(step_items)} steps")
        return create_response(201, {'id': template_id, 'name': request.template.name, 'stepsCreated': len(step_items)})

    except Exception as e:
        logger.error(f"Error importing template definition: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

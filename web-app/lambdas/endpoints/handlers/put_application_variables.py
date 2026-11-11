import lambda_init  # noqa: F401 — must be first import (pydantic)
import json
import logging
from typing import Any, Dict, List
import boto3
from pydantic import BaseModel, Field, ValidationError, field_validator
from resource_auth import require_resource_access, app_from_path
from template_definition import validation_message
from utils import create_response, get_table_name, extract_user_identity, get_current_timestamp

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VARIABLE_KEY_PATTERN = r'^[A-Za-z_][A-Za-z0-9_]*$'
MAX_APPLICATION_VARIABLES = 100


class ApplicationVariable(BaseModel):
    key: str = Field(..., pattern=VARIABLE_KEY_PATTERN)
    value: str


class ApplicationVariablesRequest(BaseModel):
    """POST /applications/{id}/variables body — replaces the whole list."""
    variables: List[ApplicationVariable] = Field(..., max_length=MAX_APPLICATION_VARIABLES)

    @field_validator('variables')
    @classmethod
    def _unique_keys(cls, variables: List[ApplicationVariable]) -> List[ApplicationVariable]:
        seen = set()
        for variable in variables:
            if variable.key in seen:
                raise ValueError(f'duplicate key {variable.key}')
            seen.add(variable.key)
        return variables


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /applications/{id}/variables — replace the application-level
    variable list (``APPLICATION#{id} / VARIABLES``). Editors of the owning
    team and up; the whole list is replaced, like use-case variables.
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path

    try:
        request = ApplicationVariablesRequest(**json.loads(event.get('body') or '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except ValidationError as e:
        return create_response(400, {'error': validation_message(e)})

    variables = [variable.model_dump() for variable in request.variables]
    user_identity = extract_user_identity(event)

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())
    table.put_item(Item={
        'pk': f'APPLICATION#{app_id}',
        'sk': 'VARIABLES',
        'variables': variables,
        'updated_at': get_current_timestamp(),
        'updated_by': user_identity.get('sub') or user_identity.get('identity', ''),
    })
    logger.info(f"Replaced application variables for {app_id} ({len(variables)} entries)")
    return create_response(200, {'variables': variables})

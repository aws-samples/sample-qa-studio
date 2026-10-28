import lambda_init  # noqa: F401 — must be first import (pydantic)
import json
import logging
from typing import Any, Dict, List
import boto3
from pydantic import BaseModel, ValidationError, field_validator
from utils import create_response, get_table_name, require_scopes, generate_uuid7, get_current_timestamp
from resource_auth import require_team_role
import permissions_repo

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class CreateApplicationRequest(BaseModel):
    """POST /applications body. teamId is the owning team (required)."""
    name: str = ''
    base_url: str = ''
    description: str = ''
    team: str = ''
    environments: List[str] = []
    teamId: str = ''

    @field_validator('name', 'base_url', 'teamId', mode='before')
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    def missing_field(self):
        """First required field that is empty, in the order clients expect."""
        for field in ('name', 'base_url', 'teamId'):
            if not getattr(self, field):
                return field
        return None


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an application owned by a team.

    Only a Team Lead of the target team (or a studio admin) may create it.
    """
    user_identity, error_response = require_scopes(event, ['api/applications.write'])
    if error_response:
        return error_response

    try:
        request = CreateApplicationRequest(**json.loads(event.get('body') or '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except ValidationError as e:
        field = '.'.join(str(p) for p in e.errors()[0]['loc'])
        return create_response(400, {'error': f'Invalid value for {field}'})

    missing = request.missing_field()
    if missing:
        return create_response(400, {'error': f'{missing} is required'})

    team_id = request.teamId
    # Role check before the existence check so non-leads can't probe team ids.
    role_err = require_team_role(user_identity, team_id, 'team_lead',
                                 'Team lead of the target team required')
    if role_err:
        return role_err
    if not permissions_repo.get_team(team_id):
        return create_response(404, {'error': 'Team not found'})

    app_id = generate_uuid7()
    now = get_current_timestamp()


    application = {
        'pk': f'APPLICATION#{app_id}',
        'sk': 'METADATA',
        'id': app_id,
        'name': request.name,
        'base_url': request.base_url,
        'description': request.description,
        'team': request.team,
        'owner_team_id': team_id,
        'environments': request.environments,
        'created_at': now,
        'updated_at': now,
        'last_execution_id': '',
        'last_execution_status': '',
        'last_execution_at': '',
        'usecase_count': 0,
    }

    # GSI2 projection so the app resolves via OWNERTEAM#{team_id} queries
    # (list_team_apps, delete_team orphaning, etc.).
    application['gsi2pk'] = f'OWNERTEAM#{team_id}'
    application['gsi2sk'] = f'APP#{app_id}'

    index_record = {
        'pk': 'APPLICATIONS',
        'sk': f'APPLICATION#{app_id}',
        'id': app_id,
        'name': request.name,
    }

    dynamodb = boto3.client('dynamodb')
    table_name = get_table_name()

    def to_dynamo(item: dict) -> dict:
        result = {}
        for k, v in item.items():
            if isinstance(v, str):
                result[k] = {'S': v}
            elif isinstance(v, bool):
                result[k] = {'BOOL': v}
            elif isinstance(v, int):
                result[k] = {'N': str(v)}
            elif isinstance(v, list):
                result[k] = {'L': [{'S': i} for i in v]}
        return result

    dynamodb.transact_write_items(
        TransactItems=[
            {'Put': {'TableName': table_name, 'Item': to_dynamo(application)}},
            {'Put': {'TableName': table_name, 'Item': to_dynamo(index_record)}},
        ]
    )

    logger.info(f"Created application {app_id}")
    return create_response(201, application)

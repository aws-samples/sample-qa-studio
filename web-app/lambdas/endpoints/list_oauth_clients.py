import json
import os
import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes
from resource_auth import has_team_role, is_studio_admin

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _load_client_records(table) -> Dict[str, dict]:
    """All OAUTH_CLIENTS records (one partition, paginated query), keyed by client id."""
    records: Dict[str, dict] = {}
    query_kwargs: Dict[str, Any] = {'KeyConditionExpression': Key('pk').eq('OAUTH_CLIENTS')}
    while True:
        response = table.query(**query_kwargs)
        for item in response.get('Items', []):
            records[item['sk']] = item
        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            return records
        query_kwargs['ExclusiveStartKey'] = last_key


def _visible_to(user_identity: dict, record: dict) -> bool:
    """Admins see every client; others only clients of teams where they are editor+."""
    if is_studio_admin(user_identity):
        return True
    team_id = (record or {}).get('team_id')
    return bool(team_id) and has_team_role(user_identity, team_id, 'editor')


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list OAuth clients in Amazon Cognito user pool.
    Requires api/oauth-clients.read or api/admin scope. Non-admins see only
    clients bound to teams where they are editor or higher.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of OAuth clients
    """
    try:
        # Validate scope (requires oauth-clients.read or admin)
        user_identity, error_response = require_scopes(event, ['api/oauth-clients.read'])
        if error_response:
            return error_response
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize clients
        cognito_client = boto3.client('cognito-idp')
        dynamodb = boto3.resource('dynamodb')
        table_name = get_table_name()
        table = dynamodb.Table(table_name)
        
        client_records = _load_client_records(table)

        # List all user pool clients
        clients_list = []
        next_token = None
        
        while True:
            if next_token:
                response = cognito_client.list_user_pool_clients(
                    UserPoolId=user_pool_id,
                    MaxResults=60,
                    NextToken=next_token
                )
            else:
                response = cognito_client.list_user_pool_clients(
                    UserPoolId=user_pool_id,
                    MaxResults=60
                )
            
            # Get detailed information for each client
            for client_summary in response.get('UserPoolClients', []):
                client_id = client_summary.get('ClientId')
                record = client_records.get(client_id)
                if not _visible_to(user_identity, record):
                    continue
                
                try:
                    client_details = cognito_client.describe_user_pool_client(
                        UserPoolId=user_pool_id,
                        ClientId=client_id
                    )
                    
                    client = client_details.get('UserPoolClient', {})
                    
                    # Format dates
                    created_date = client.get('CreationDate')
                    last_modified_date = client.get('LastModifiedDate')
                    
                    record = record or {}
                    
                    clients_list.append({
                        'client_id': client.get('ClientId', ''),
                        'client_name': client.get('ClientName', ''),
                        'created_date': created_date.isoformat() if created_date else None,
                        'last_modified_date': last_modified_date.isoformat() if last_modified_date else None,
                        'created_by': record.get('created_by'),
                        'team_id': record.get('team_id'),
                        'refresh_token_validity': client.get('RefreshTokenValidity'),
                        'access_token_validity': client.get('AccessTokenValidity'),
                        'id_token_validity': client.get('IdTokenValidity'),
                        'token_validity_units': client.get('TokenValidityUnits', {}),
                        'explicit_auth_flows': client.get('ExplicitAuthFlows', []),
                        'allowed_oauth_flows': client.get('AllowedOAuthFlows', []),
                        'allowed_oauth_scopes': client.get('AllowedOAuthScopes', []),
                        'enabled': True  # Amazon Cognito doesn't have a disabled state, all clients are enabled
                    })
                except Exception as e:
                    logger.warning(f"Failed to get details for client {client_id}: {str(e)}")
                    continue
            
            next_token = response.get('NextToken')
            if not next_token:
                break
        
        result = {
            'clients': clients_list,
            'count': len(clients_list)
        }
        
        return create_response(200, result)
        
    except cognito_client.exceptions.ResourceNotFoundException as e:
        logger.error(f"User pool not found: {str(e)}")
        return create_response(404, {'error': 'User pool not found'})
    except Exception as e:
        logger.error(f"Error listing OAuth clients: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

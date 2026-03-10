import json
import os
import boto3
from utils import create_response, require_scopes

cognito = boto3.client('cognito-idp')

def handler(event, context):
    """
    List available OAuth scopes from the Cognito resource server.
    Requires api/oauth-clients.read scope.
    
    Returns:
    - 200: List of available scopes with descriptions
    - 403: Missing required scope
    - 500: Error fetching scopes
    """
    try:
        # Validate scope
        user_identity, error_response = require_scopes(event, ['api/oauth-clients.read'])
        if error_response:
            return error_response

        user_pool_id = os.environ.get('USER_POOL_ID')
        resource_server_identifier = os.environ.get('RESOURCE_SERVER_IDENTIFIER', 'api')
        
        if not user_pool_id:
            return create_response(500, {'error': 'USER_POOL_ID not configured'})
        
        # Fetch resource server details from Amazon Cognito
        response = cognito.describe_resource_server(
            UserPoolId=user_pool_id,
            Identifier=resource_server_identifier
        )
        
        resource_server = response.get('ResourceServer', {})
        scopes = resource_server.get('Scopes', [])
        
        # Transform scopes to include full scope name (api/scope_name)
        formatted_scopes = [
            {
                'value': f'{resource_server_identifier}/{scope["ScopeName"]}',
                'label': f'{resource_server_identifier}/{scope["ScopeName"]}',
                'description': scope.get('ScopeDescription', '')
            }
            for scope in scopes
        ]
        
        return create_response(200, {
            'scopes': formatted_scopes,
            'resource_server_identifier': resource_server_identifier
        })
        
    except cognito.exceptions.ResourceNotFoundException:
        return create_response(404, {'error': 'Resource server not found'})
    except Exception as e:
        print(f'Error fetching scopes: {str(e)}')
        return create_response(500, {'error': 'Failed to fetch scopes'})

import json
import os
import boto3
from utils import create_response

cognito = boto3.client('cognito-idp')

def handler(event, context):
    """
    List available OAuth scopes from the Cognito resource server.
    This endpoint is public (no authentication required) to allow
    the OAuth client creation form to display available scopes.
    
    Returns:
    - 200: List of available scopes with descriptions
    - 500: Error fetching scopes
    """
    try:
        user_pool_id = os.environ.get('USER_POOL_ID')
        resource_server_identifier = os.environ.get('RESOURCE_SERVER_IDENTIFIER', 'api')
        
        if not user_pool_id:
            return create_response(500, {'error': 'USER_POOL_ID not configured'})
        
        # Fetch resource server details from Cognito
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

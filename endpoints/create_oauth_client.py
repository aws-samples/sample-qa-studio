import json
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create an OAuth client in Cognito User Pool.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created OAuth client info including secret
    """
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        client_name = body.get('clientName')
        description = body.get('description', '')
        
        if not client_name:
            return create_response(400, {'error': 'Client name is required'})
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Create OAuth client with client credentials flow
        response = cognito_client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName=client_name,
            GenerateSecret=True,  # Generate client secret for OAuth
            ExplicitAuthFlows=[],  # No user auth flows
            AllowedOAuthFlows=['client_credentials'],
            AllowedOAuthFlowsUserPoolClient=True,
            AllowedOAuthScopes=[
                # Add your custom scopes here or use resource server scopes
                # For now, we'll use standard scopes
            ],
            PreventUserExistenceErrors='ENABLED'
        )
        
        client_data = response.get('UserPoolClient', {})
        
        result = {
            'clientId': client_data.get('ClientId', ''),
            'clientSecret': client_data.get('ClientSecret', ''),  # Only returned on creation
            'clientName': client_data.get('ClientName', ''),
            'createdAt': client_data.get('CreationDate').isoformat() if client_data.get('CreationDate') else None,
            'allowedOAuthFlows': client_data.get('AllowedOAuthFlows', []),
            'allowedOAuthScopes': client_data.get('AllowedOAuthScopes', [])
        }
        
        logger.info(f"Created OAuth client: {client_name} (ID: {result['clientId']})")
        
        return create_response(201, result)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating OAuth client: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

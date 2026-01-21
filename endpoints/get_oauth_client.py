import os
import logging
from typing import Any, Dict
from urllib.parse import unquote
import boto3
from utils import create_response

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get details of an OAuth client from Cognito User Pool.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with OAuth client details
    """
    try:
        # Get client ID from path parameters
        encoded_client_id = event.get('pathParameters', {}).get('id')
        if not encoded_client_id:
            logger.error("Client ID parameter is required")
            return create_response(400, {'error': 'Client ID is required'})
        
        # URL decode the client ID
        client_id = unquote(encoded_client_id)
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Get client details
        response = cognito_client.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=client_id
        )
        
        client_data = response.get('UserPoolClient', {})
        
        # Verify this is an OAuth client
        allowed_flows = client_data.get('AllowedOAuthFlows', [])
        if 'client_credentials' not in allowed_flows:
            return create_response(404, {'error': 'OAuth client not found'})
        
        result = {
            'clientId': client_data.get('ClientId', ''),
            'clientName': client_data.get('ClientName', ''),
            'createdAt': client_data.get('CreationDate').isoformat() if client_data.get('CreationDate') else None,
            'lastModified': client_data.get('LastModifiedDate').isoformat() if client_data.get('LastModifiedDate') else None,
            'allowedOAuthFlows': allowed_flows,
            'allowedOAuthScopes': client_data.get('AllowedOAuthScopes', [])
        }
        
        return create_response(200, result)
        
    except cognito_client.exceptions.ResourceNotFoundException:
        logger.error(f"OAuth client not found: {encoded_client_id}")
        return create_response(404, {'error': 'OAuth client not found'})
    except Exception as e:
        logger.error(f"Error getting OAuth client '{encoded_client_id}': {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

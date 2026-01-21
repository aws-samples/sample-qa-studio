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
    Lambda handler to delete an OAuth client from Cognito User Pool.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
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
        
        # Verify this is an OAuth client before deleting
        try:
            response = cognito_client.describe_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=client_id
            )
            
            client_data = response.get('UserPoolClient', {})
            allowed_flows = client_data.get('AllowedOAuthFlows', [])
            
            if 'client_credentials' not in allowed_flows:
                return create_response(404, {'error': 'OAuth client not found'})
        except cognito_client.exceptions.ResourceNotFoundException:
            return create_response(404, {'error': 'OAuth client not found'})
        
        # Delete the OAuth client
        cognito_client.delete_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=client_id
        )
        
        logger.info(f"Deleted OAuth client: {client_id}")
        
        # Return 204 No Content (successful deletion with no body)
        return {
            'statusCode': 204,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': ''
        }
        
    except Exception as e:
        logger.error(f"Error deleting OAuth client '{encoded_client_id}': {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Failed to delete OAuth client'})

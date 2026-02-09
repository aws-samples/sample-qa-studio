import json
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_user_token

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete an OAuth client from Cognito User Pool.
    Only accessible with user tokens, not M2M tokens.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response confirming deletion
    """
    try:
        # Validate user token (M2M tokens not allowed)
        user_identity, error_response = require_user_token(event)
        if error_response:
            return error_response
        
        # Get client ID from path parameters
        path_parameters = event.get('pathParameters', {})
        client_id = path_parameters.get('clientId')
        
        if not client_id:
            return create_response(400, {'error': 'Client ID is required'})
        
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
        
        # Check if client has created_by metadata
        try:
            metadata_response = table.get_item(
                Key={
                    'pk': 'OAUTH_CLIENTS',
                    'sk': client_id
                }
            )
            
            if 'Item' not in metadata_response or not metadata_response['Item'].get('created_by'):
                logger.warning(f"Attempted to delete OAuth client without created_by: {client_id}")
                return create_response(403, {
                    'error': 'Cannot delete this OAuth client',
                    'message': 'Only OAuth clients created through the application can be deleted'
                })
        except Exception as e:
            logger.error(f"Error checking client metadata: {str(e)}")
            return create_response(403, {
                'error': 'Cannot delete this OAuth client',
                'message': 'Only OAuth clients created through the application can be deleted'
            })
        
        # Delete OAuth client from Cognito
        try:
            cognito_client.delete_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=client_id
            )
            logger.info(f"Successfully deleted OAuth client from Cognito: {client_id}")
        except cognito_client.exceptions.ResourceNotFoundException:
            logger.warning(f"OAuth client not found in Cognito: {client_id}")
            # Continue to delete from DynamoDB even if not in Cognito
        
        # Delete metadata from DynamoDB
        try:
            table.delete_item(
                Key={
                    'pk': 'OAUTH_CLIENTS',
                    'sk': client_id
                }
            )
            logger.info(f"Deleted OAuth client metadata from DynamoDB for client: {client_id}")
        except Exception as e:
            logger.error(f"Failed to delete metadata for client {client_id}: {str(e)}", exc_info=True)
            # Return error since metadata deletion failed
            return create_response(500, {
                'error': 'Failed to delete OAuth client metadata',
                'message': 'The client was deleted from Cognito but metadata cleanup failed. Please contact support.'
            })
        
        return create_response(200, {
            'message': 'OAuth client deleted successfully',
            'client_id': client_id
        })
        
    except Exception as e:
        logger.error(f"Error deleting OAuth client: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

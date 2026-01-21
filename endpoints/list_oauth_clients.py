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
    Lambda handler to list OAuth clients from Cognito User Pool.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of OAuth clients
    """
    try:
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # List all user pool clients
        response = cognito_client.list_user_pool_clients(
            UserPoolId=user_pool_id,
            MaxResults=60
        )
        
        # Get detailed information for each client
        clients = []
        for client_summary in response.get('UserPoolClients', []):
            client_id = client_summary.get('ClientId')
            
            # Skip if this is not an OAuth client (check by getting details)
            try:
                client_details = cognito_client.describe_user_pool_client(
                    UserPoolId=user_pool_id,
                    ClientId=client_id
                )
                
                client_data = client_details.get('UserPoolClient', {})
                
                # Only include clients with client credentials flow (OAuth clients)
                allowed_flows = client_data.get('AllowedOAuthFlows', [])
                if 'client_credentials' in allowed_flows:
                    clients.append({
                        'clientId': client_id,
                        'clientName': client_data.get('ClientName', ''),
                        'createdAt': client_data.get('CreationDate').isoformat() if client_data.get('CreationDate') else None,
                        'lastModified': client_data.get('LastModifiedDate').isoformat() if client_data.get('LastModifiedDate') else None,
                        'allowedOAuthFlows': allowed_flows,
                        'allowedOAuthScopes': client_data.get('AllowedOAuthScopes', [])
                    })
            except Exception as e:
                logger.warning(f"Error getting details for client {client_id}: {str(e)}")
                continue
        
        return create_response(200, {'clients': clients})
        
    except Exception as e:
        logger.error(f"Error listing OAuth clients: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

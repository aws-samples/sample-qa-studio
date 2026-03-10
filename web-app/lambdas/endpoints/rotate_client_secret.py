import json
import os
import logging
from typing import Any, Dict
from datetime import datetime
import boto3
from utils import create_response, get_table_name, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to rotate an OAuth client secret by recreating the Amazon Cognito app client.
    Requires api/oauth-clients.write or api/admin scope.
    
    SECURITY: Only the user who created the client can rotate its secret.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with new client_id and client_secret
    """
    try:
        # Validate scope (requires oauth-clients.write or admin)
        user_identity, error_response = require_scopes(event, ['api/oauth-clients.write'])
        if error_response:
            return error_response
        
        requesting_user = user_identity.get('identity', 'unknown')
        logger.info(f"Rotating OAuth client secret - requested by: {requesting_user}")
        
        # Get client ID from path parameters
        path_parameters = event.get('pathParameters', {})
        old_client_id = path_parameters.get('clientId')
        
        if not old_client_id:
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
        
        # Verify user owns this client via DynamoDB metadata
        try:
            metadata_response = table.get_item(
                Key={
                    'pk': 'OAUTH_CLIENTS',
                    'sk': old_client_id
                }
            )
            
            if 'Item' not in metadata_response:
                logger.warning(f"OAuth client metadata not found: {old_client_id}")
                return create_response(404, {'error': 'OAuth client not found'})
            
            metadata = metadata_response['Item']
            created_by = metadata.get('created_by')
            
            if not created_by:
                logger.warning(f"OAuth client has no created_by field: {old_client_id}")
                return create_response(403, {
                    'error': 'Cannot rotate secret for this OAuth client',
                    'message': 'Only OAuth clients created through the application can be rotated'
                })
            
            # Check ownership (unless user has admin scope)
            has_admin = 'api/admin' in user_identity.get('scopes', [])
            if not has_admin and created_by != requesting_user:
                logger.warning(f"User {requesting_user} attempted to rotate client owned by {created_by}")
                return create_response(403, {
                    'error': 'Forbidden: Cannot rotate secret for OAuth client you do not own',
                    'message': f'This client was created by {created_by}'
                })
                
        except Exception as e:
            logger.error(f"Error checking client metadata: {str(e)}")
            return create_response(500, {'error': 'Failed to verify client ownership'})
        
        # Fetch current client configuration from Amazon Cognito
        try:
            client_details = cognito_client.describe_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=old_client_id
            )
            old_client = client_details.get('UserPoolClient', {})
            
            client_name = old_client.get('ClientName', '')
            allowed_oauth_scopes = old_client.get('AllowedOAuthScopes', [])
            refresh_token_validity = old_client.get('RefreshTokenValidity', 30)
            access_token_validity = old_client.get('AccessTokenValidity', 60)
            id_token_validity = old_client.get('IdTokenValidity', 60)
            token_validity_units = old_client.get('TokenValidityUnits', {
                'AccessToken': 'minutes',
                'IdToken': 'minutes',
                'RefreshToken': 'days'
            })
            explicit_auth_flows = old_client.get('ExplicitAuthFlows', [
                'ALLOW_REFRESH_TOKEN_AUTH',
                'ALLOW_USER_PASSWORD_AUTH',
                'ALLOW_USER_SRP_AUTH'
            ])
            
            logger.info(f"Fetched configuration for client: {client_name}")
            
        except cognito_client.exceptions.ResourceNotFoundException:
            logger.error(f"OAuth client not found in Amazon Cognito: {old_client_id}")
            return create_response(404, {'error': 'OAuth client not found in Amazon Cognito'})
        except Exception as e:
            logger.error(f"Error fetching client configuration: {str(e)}")
            return create_response(500, {'error': 'Failed to fetch client configuration'})
        
        # Delete old Amazon Cognito app client
        try:
            cognito_client.delete_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=old_client_id
            )
            logger.info(f"Deleted old OAuth client from Amazon Cognito: {old_client_id}")
        except Exception as e:
            logger.error(f"Error deleting old client: {str(e)}")
            return create_response(500, {'error': 'Failed to delete old client'})
        
        # Create new Amazon Cognito app client with same settings
        try:
            response = cognito_client.create_user_pool_client(
                UserPoolId=user_pool_id,
                ClientName=client_name,
                GenerateSecret=True,
                RefreshTokenValidity=refresh_token_validity,
                AccessTokenValidity=access_token_validity,
                IdTokenValidity=id_token_validity,
                TokenValidityUnits=token_validity_units,
                ExplicitAuthFlows=explicit_auth_flows,
                AllowedOAuthFlows=['client_credentials'],
                AllowedOAuthScopes=allowed_oauth_scopes,
                AllowedOAuthFlowsUserPoolClient=True,
                SupportedIdentityProviders=['COGNITO'],
                PreventUserExistenceErrors='ENABLED',
                EnableTokenRevocation=True,
                EnablePropagateAdditionalUserContextData=False
            )
            
            new_client = response.get('UserPoolClient', {})
            new_client_id = new_client.get('ClientId', '')
            new_client_secret = new_client.get('ClientSecret', '')
            
            logger.info(f"Created new OAuth client in Amazon Cognito: {new_client_id}")
            
        except Exception as e:
            logger.error(f"Error creating new client: {str(e)}")
            return create_response(500, {
                'error': 'Failed to create new client',
                'message': 'Old client has been deleted. Please create a new client manually.'
            })
        
        # Update DynamoDB metadata with new client_id
        try:
            # Delete old metadata
            table.delete_item(
                Key={
                    'pk': 'OAUTH_CLIENTS',
                    'sk': old_client_id
                }
            )
            
            # Create new metadata with new client_id
            rotated_at = datetime.utcnow().isoformat()
            oauth_client_item = {
                'pk': 'OAUTH_CLIENTS',
                'sk': new_client_id,
                'client_id': new_client_id,
                'client_name': metadata.get('client_name', client_name),
                'created_by': created_by,
                'created_at': metadata.get('created_at', rotated_at),
                'rotated_at': rotated_at,
                'entity_type': 'oauth_client'
            }
            
            table.put_item(Item=oauth_client_item)
            logger.info(f"Updated OAuth client metadata in DynamoDB: {new_client_id}")
            
        except Exception as e:
            logger.error(f"Error updating metadata: {str(e)}")
            # Log error but don't fail - new client is functional
            logger.warning(f"Metadata update failed but new client {new_client_id} is functional")
        
        result = {
            'client_id': new_client_id,
            'client_secret': new_client_secret,  # Only shown once
            'rotated_at': rotated_at
        }
        
        logger.info(f"Successfully rotated OAuth client secret: {client_name} by {requesting_user}")
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error rotating OAuth client secret: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

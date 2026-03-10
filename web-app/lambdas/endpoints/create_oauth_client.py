import json
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Default scopes for OAuth clients (minimal permissions)
DEFAULT_SCOPES = ['api/usecases.execute']


def get_valid_scopes_from_cognito(user_pool_id: str, resource_server_identifier: str = 'api') -> list[str]:
    """
    Fetch valid OAuth scopes from Amazon Cognito resource server.
    
    Args:
        user_pool_id: Cognito User Pool ID
        resource_server_identifier: Resource server identifier (default: 'api')
        
    Returns:
        List of valid scope strings (e.g., ['api/usecases.read', 'api/usecases.write'])
    """
    try:
        cognito_client = boto3.client('cognito-idp')
        response = cognito_client.describe_resource_server(
            UserPoolId=user_pool_id,
            Identifier=resource_server_identifier
        )
        
        resource_server = response.get('ResourceServer', {})
        scopes = resource_server.get('Scopes', [])
        
        # Format scopes as 'api/scope_name'
        valid_scopes = [
            f'{resource_server_identifier}/{scope["ScopeName"]}'
            for scope in scopes
        ]
        
        logger.info(f"Fetched {len(valid_scopes)} valid scopes from Amazon Cognito: {valid_scopes}")
        return valid_scopes
        
    except Exception as e:
        logger.error(f"Error fetching scopes from Amazon Cognito: {str(e)}")
        # Return empty list on error - validation fails gracefully
        return []


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create an OAuth client in Amazon Cognito user pool.
    Requires api/oauth-clients.write or api/admin scope.
    
    SECURITY: Users can only grant scopes they already possess to prevent privilege escalation.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created OAuth client info
    """
    try:
        # Validate scope (requires oauth-clients.write or admin)
        user_identity, error_response = require_scopes(event, ['api/oauth-clients.write'])
        if error_response:
            return error_response
        
        created_by = user_identity.get('identity', 'unknown')
        creator_scopes = user_identity.get('scopes', [])
        has_admin = 'api/admin' in creator_scopes
        
        logger.info(f"Creating OAuth client - user_identity: {user_identity}")
        logger.info(f"Created by: {created_by}, Creator scopes: {creator_scopes}")
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        client_name = body.get('name')
        requested_scopes = body.get('scopes', DEFAULT_SCOPES)
        
        if not client_name:
            return create_response(400, {'error': 'Client name is required'})
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        resource_server_identifier = os.environ.get('RESOURCE_SERVER_IDENTIFIER', 'api')
        
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Fetch valid scopes from Amazon Cognito
        valid_scopes = get_valid_scopes_from_cognito(user_pool_id, resource_server_identifier)
        
        if not valid_scopes:
            logger.error("Failed to fetch valid scopes from Cognito")
            return create_response(500, {'error': 'Failed to validate scopes'})
        
        # Validate requested scopes
        if not isinstance(requested_scopes, list):
            return create_response(400, {'error': 'Scopes must be an array'})
        
        if not requested_scopes:
            return create_response(400, {'error': 'At least one scope must be specified'})
        
        invalid_scopes = [s for s in requested_scopes if s not in valid_scopes]
        if invalid_scopes:
            return create_response(400, {
                'error': f'Invalid scopes: {", ".join(invalid_scopes)}',
                'valid_scopes': valid_scopes
            })
        
        # SECURITY CHECK: Prevent privilege escalation
        # Users can only grant scopes they already have (unless they have admin scope)
        if not has_admin:
            unauthorized_scopes = [s for s in requested_scopes if s not in creator_scopes]
            if unauthorized_scopes:
                logger.warning(f"Privilege escalation attempt by {created_by}: tried to grant {unauthorized_scopes} but only has {creator_scopes}")
                return create_response(403, {
                    'error': 'Forbidden: Cannot grant scopes you do not possess',
                    'message': f'You cannot grant the following scopes: {", ".join(unauthorized_scopes)}',
                    'your_scopes': creator_scopes,
                    'requested_scopes': requested_scopes
                })
        
        logger.info(f"Creating OAuth client with scopes: {requested_scopes}")
        
        # Initialize Amazon Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Create OAuth client in Amazon Cognito user pool
        response = cognito_client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName=client_name,
            GenerateSecret=True,
            RefreshTokenValidity=30,
            AccessTokenValidity=60,
            IdTokenValidity=60,
            TokenValidityUnits={
                'AccessToken': 'minutes',
                'IdToken': 'minutes',
                'RefreshToken': 'days'
            },
            ExplicitAuthFlows=[
                'ALLOW_REFRESH_TOKEN_AUTH',
                'ALLOW_USER_PASSWORD_AUTH',
                'ALLOW_USER_SRP_AUTH'
            ],
            AllowedOAuthFlows=[
                'client_credentials'
            ],
            AllowedOAuthScopes=requested_scopes,
            AllowedOAuthFlowsUserPoolClient=True,
            SupportedIdentityProviders=['COGNITO'],
            PreventUserExistenceErrors='ENABLED',
            EnableTokenRevocation=True,
            EnablePropagateAdditionalUserContextData=False
        )
        
        user_pool_client = response.get('UserPoolClient', {})
        client_id = user_pool_client.get('ClientId', '')
        created_date = user_pool_client.get('CreationDate')
        
        # Store OAuth client metadata in DynamoDB
        try:
            table_name = get_table_name()
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(table_name)
            
            oauth_client_item = {
                'pk': 'OAUTH_CLIENTS',
                'sk': client_id,
                'client_id': client_id,
                'client_name': client_name,
                'created_by': created_by,
                'created_at': created_date.isoformat() if created_date else get_current_timestamp(),
                'entity_type': 'oauth_client'
            }
            
            table.put_item(Item=oauth_client_item)
            logger.info(f"Stored OAuth client metadata in DynamoDB for client: {client_id}")
        except Exception as dynamodb_error:
            # If DynamoDB write fails, clean up the Cognito client to avoid orphaned resources
            logger.error(f"Failed to store OAuth client metadata in DynamoDB: {str(dynamodb_error)}")
            try:
                cognito_client.delete_user_pool_client(
                    UserPoolId=user_pool_id,
                    ClientId=client_id
                )
                logger.info(f"Rolled back Cognito client creation for client: {client_id}")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback Cognito client: {str(rollback_error)}")
            
            return create_response(500, {'error': 'Failed to create OAuth client metadata'})
        
        result = {
            'client_id': client_id,
            'client_name': user_pool_client.get('ClientName', ''),
            'client_secret': user_pool_client.get('ClientSecret', ''),
            'scopes': requested_scopes,
            'created_date': created_date.isoformat() if created_date else None,
            'created_by': created_by,
            'refresh_token_validity': user_pool_client.get('RefreshTokenValidity'),
            'access_token_validity': user_pool_client.get('AccessTokenValidity'),
            'id_token_validity': user_pool_client.get('IdTokenValidity')
        }
        
        logger.info(f"Successfully created OAuth client: {client_name} with scopes {requested_scopes} by {created_by}")
        return create_response(201, result)
        
    except cognito_client.exceptions.InvalidParameterException as e:
        logger.error(f"Invalid parameter: {str(e)}")
        return create_response(400, {'error': f'Invalid parameter: {str(e)}'})
    except cognito_client.exceptions.ResourceNotFoundException as e:
        logger.error(f"User pool not found: {str(e)}")
        return create_response(404, {'error': 'User pool not found'})
    except cognito_client.exceptions.LimitExceededException as e:
        logger.error(f"Limit exceeded: {str(e)}")
        return create_response(429, {'error': 'Too many OAuth clients. Please delete unused clients.'})
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating OAuth client: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

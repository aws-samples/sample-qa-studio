import json
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_user_token

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create an OAuth client in Cognito User Pool.
    Only accessible with user tokens, not M2M tokens.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created OAuth client info
    """
    try:
        # Validate user token (M2M tokens not allowed)
        user_identity, error_response = require_user_token(event)
        if error_response:
            return error_response
        
        created_by = user_identity.get('identity', 'unknown')
        logger.info(f"Creating OAuth client - user_identity: {user_identity}")
        logger.info(f"Created by: {created_by}")
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        client_name = body.get('name')
        
        if not client_name:
            return create_response(400, {'error': 'Client name is required'})
        
        # Get user pool ID from environment
        user_pool_id = os.environ.get('USER_POOL_ID')
        if not user_pool_id:
            logger.error("USER_POOL_ID environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Cognito client
        cognito_client = boto3.client('cognito-idp')
        
        # Create OAuth client in Cognito User Pool
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
            AllowedOAuthScopes=[
                'api/execute'
            ],
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
            
            logger.info(f"Storing OAuth client item: {oauth_client_item}")
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
            'created_date': created_date.isoformat() if created_date else None,
            'created_by': created_by,
            'refresh_token_validity': user_pool_client.get('RefreshTokenValidity'),
            'access_token_validity': user_pool_client.get('AccessTokenValidity'),
            'id_token_validity': user_pool_client.get('IdTokenValidity')
        }
        
        logger.info(f"Successfully created OAuth client: {client_name} by {created_by}")
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

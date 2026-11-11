import logging
import os
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key, Attr
from utils import create_response, get_table_name, extract_user_identity
from resource_auth import require_resource_access, usecase_from_path
from sns_filter_policy import find_email_subscription, remove_usecase

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to unsubscribe a user from usecase notifications.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with subscription status
    """
    try:
        user_identity = extract_user_identity(event)
        # Get user email from identity (fallback to username if no email)
        user_email = user_identity.get('email') or user_identity.get('identity', 'unknown')
        
        # Get usecase ID from path
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        sns_client = boto3.client('sns')
        
        # Find and delete the subscription records for this user and usecase
        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('NOTIFICATION#'),
            FilterExpression=Attr('email').eq(user_email)
        )
        
        # Delete all subscription records for this user and usecase
        deleted_count = 0
        for item in response.get('Items', []):
            table.delete_item(
                Key={
                    'pk': item['pk'],
                    'sk': item['sk']
                }
            )
            deleted_count += 1
        
        logger.info(f"Deleted {deleted_count} DynamoDB records for usecase {usecase_id}")
        
        # Update SNS filter policy to remove this usecase from the user's subscription
        logger.info(f"Calling remove_usecase_from_filter_policy for usecase {usecase_id}")
        remove_usecase_from_filter_policy(sns_client, user_email, usecase_id)
        
        # Return subscription status
        return create_response(200, {
            'is_subscribed': False,
            'email': user_email
        })
        
    except Exception as e:
        logger.error(f"Error unsubscribing from usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def remove_usecase_from_filter_policy(sns_client, email: str, usecase_id_to_remove: str):
    """Remove the use case from ``email``'s filter policy (unsubscribing when it
    was the last one). Never fails the request: SNS errors are logged."""
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if not topic_arn:
        logger.info("SNS_TOPIC_ARN not set, skipping SNS filter policy update")
        return

    try:
        subscription_arn = find_email_subscription(sns_client, topic_arn, email, confirmed_only=True)
        if not subscription_arn:
            logger.info("No confirmed SNS subscription found")
            return  # Not an error - user might not have SNS subscription
        remove_usecase(sns_client, subscription_arn, usecase_id_to_remove)
    except Exception as e:
        logger.error(f"Error: Could not update SNS filter policy: {str(e)}", exc_info=True)
        # Continue anyway - don't fail the unsubscribe operation

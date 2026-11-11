import logging
import os
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import create_response, get_table_name, get_current_timestamp, extract_user_identity
from resource_auth import require_resource_access, usecase_from_path
from sns_filter_policy import (
    PENDING_CONFIRMATION, add_usecase, filter_policy_json, find_email_subscription,
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to subscribe a user to usecase notifications.
    
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
        
        # Create subscription record in DynamoDB
        subscription = {
            'pk': f'USECASE#{usecase_id}',
            'sk': f'NOTIFICATION#{uuid4()}',
            'email': user_email,
            'created_at': get_current_timestamp()
        }
        
        table.put_item(Item=subscription)
        logger.info(f"Created subscription record for usecase {usecase_id}")
        
        # Subscribe user to SNS topic and set/update filter policy
        configure_sns_subscription_with_filter(sns_client, table, user_email, usecase_id)
        
        # Return subscription status
        return create_response(201, {
            'is_subscribed': True,
            'email': user_email
        })
        
    except Exception as e:
        logger.error(f"Error subscribing to usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def configure_sns_subscription_with_filter(sns_client, table, email: str, usecase_id: str):
    """Subscribe ``email`` to the topic (filtered to this use case) or add the
    use case to an existing confirmed subscription's filter policy.

    Never fails the request: SNS errors are logged.
    """
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if not topic_arn:
        logger.info("SNS_TOPIC_ARN not set, skipping SNS subscription")
        return

    try:
        subscription_arn = find_email_subscription(sns_client, topic_arn, email, confirmed_only=False)
        if subscription_arn is None:
            response = sns_client.subscribe(
                TopicArn=topic_arn,
                Protocol='email',
                Endpoint=email,
                Attributes={'FilterPolicy': filter_policy_json([usecase_id])},
            )
            logger.info(f"Subscribed to SNS topic. Subscription ARN: {response.get('SubscriptionArn')}")
        elif subscription_arn == PENDING_CONFIRMATION:
            logger.info("Subscription pending confirmation - filter policy is updated after confirmation")
        else:
            add_usecase(sns_client, subscription_arn, usecase_id)
    except Exception as e:
        logger.error(f"Error ensuring SNS subscription with filter: {str(e)}", exc_info=True)
        # Continue anyway - don't fail the usecase subscription

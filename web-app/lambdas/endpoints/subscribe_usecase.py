import logging
import json
import os
from typing import Any, Dict, List
from uuid import uuid4
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_current_timestamp, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
        # Validate scopes (write permission needed to modify subscriptions)
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        # Get user email from identity (fallback to username if no email)
        user_email = user_identity.get('email') or user_identity.get('identity', 'unknown')
        
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        
        if not usecase_id:
            return create_response(400, {'error': 'Usecase ID is required'})
        
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
        logger.info(f"Created subscription record for {user_email} to usecase {usecase_id}")
        
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
    """
    Subscribe user to SNS topic and set/update filter policy for this usecase.
    
    Args:
        sns_client: Boto3 SNS client
        table: DynamoDB table resource
        email: User email address
        usecase_id: Usecase ID to subscribe to
    """
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if not topic_arn:
        logger.info("SNS_TOPIC_ARN not set, skipping SNS subscription")
        return
    
    try:
        # Check if user is already subscribed
        response = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
        
        subscription_arn = None
        existing_subscription = False
        
        for subscription in response.get('Subscriptions', []):
            if subscription.get('Endpoint') == email and subscription.get('Protocol') == 'email':
                subscription_arn = subscription.get('SubscriptionArn')
                existing_subscription = True
                logger.info(f"User {email} already subscribed to SNS topic with ARN: {subscription_arn}")
                break
        
        # If not subscribed, subscribe with initial filter policy
        if not existing_subscription:
            initial_filter_policy = create_filter_policy_json([usecase_id])
            
            subscribe_response = sns_client.subscribe(
                TopicArn=topic_arn,
                Protocol='email',
                Endpoint=email,
                Attributes={
                    'FilterPolicy': initial_filter_policy
                }
            )
            
            subscription_arn = subscribe_response.get('SubscriptionArn')
            logger.info(f"Successfully subscribed {email} to SNS topic with filter policy {initial_filter_policy}. Subscription ARN: {subscription_arn}")
        else:
            # For existing subscriptions, update the filter policy to include the new usecase
            if subscription_arn and subscription_arn != 'PendingConfirmation':
                update_filter_policy_for_user(sns_client, table, email, usecase_id)
            else:
                logger.info(f"Subscription pending confirmation for {email} - filter policy is updated after confirmation")
    
    except Exception as e:
        logger.error(f"Error ensuring SNS subscription with filter: {str(e)}", exc_info=True)
        # Continue anyway - don't fail the usecase subscription


def update_filter_policy_for_user(sns_client, table, email: str, usecase_id: str):
    """
    Update the SNS filter policy to include a new usecase for the user.
    
    Args:
        sns_client: Boto3 SNS client
        table: DynamoDB table resource
        email: User email address
        usecase_id: Usecase ID to add to filter
    """
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if not topic_arn:
        raise Exception("SNS_TOPIC_ARN not set")
    
    # Find the user's subscription
    response = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
    
    subscription_arn = None
    for subscription in response.get('Subscriptions', []):
        if (subscription.get('Endpoint') == email and 
            subscription.get('Protocol') == 'email' and 
            subscription.get('SubscriptionArn') != 'PendingConfirmation'):
            subscription_arn = subscription.get('SubscriptionArn')
            break
    
    if not subscription_arn:
        raise Exception(f"No confirmed subscription found for {email}")
    
    # Get current filter policy from SNS subscription (ONLY source of truth)
    current_usecases = get_current_filter_policy_usecases(sns_client, subscription_arn)
    logger.info(f"Current SNS filter policy usecases for {email}: {current_usecases}")
    
    # Add the new usecase if not already in the list
    if usecase_id not in current_usecases:
        current_usecases.append(usecase_id)
    
    # Create filter policy JSON with updated usecases
    filter_policy = create_filter_policy_json(current_usecases)
    logger.info(f"Setting filter policy for {email} with usecases {current_usecases}: {filter_policy}")
    
    # Set the filter policy
    sns_client.set_subscription_attributes(
        SubscriptionArn=subscription_arn,
        AttributeName='FilterPolicy',
        AttributeValue=filter_policy
    )
    
    logger.info(f"Successfully set filter policy for {email}: {filter_policy}")


def get_current_filter_policy_usecases(sns_client, subscription_arn: str) -> List[str]:
    """
    Get the current usecase_id array from SNS filter policy.
    
    Args:
        sns_client: Boto3 SNS client
        subscription_arn: SNS subscription ARN
        
    Returns:
        List of usecase IDs in the current filter policy
    """
    try:
        response = sns_client.get_subscription_attributes(SubscriptionArn=subscription_arn)
        
        filter_policy_str = response.get('Attributes', {}).get('FilterPolicy')
        if not filter_policy_str:
            logger.info(f"No existing filter policy found for subscription {subscription_arn}")
            return []
        
        logger.info(f"Current filter policy: {filter_policy_str}")
        
        # Parse the filter policy JSON
        filter_policy = json.loads(filter_policy_str)
        logger.info(f"Parsed filter policy: {filter_policy}")
        
        # Extract usecase_id array
        usecases = filter_policy.get('usecase_id', [])
        logger.info(f"Final parsed usecases: {usecases}")
        
        return usecases
        
    except Exception as e:
        logger.warning(f"Could not get current filter policy, starting fresh: {str(e)}")
        return []


def create_filter_policy_json(usecase_ids: List[str]) -> str:
    """
    Create the SNS filter policy JSON for multiple usecases.
    
    Args:
        usecase_ids: List of usecase IDs
        
    Returns:
        JSON string for SNS filter policy
    """
    return json.dumps({'usecase_id': usecase_ids})

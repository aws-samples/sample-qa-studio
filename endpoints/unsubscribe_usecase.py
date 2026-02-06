import logging
import json
import os
from typing import Any, Dict, List
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from utils import create_response, get_table_name

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        
        if not usecase_id:
            return create_response(400, {'error': 'Usecase ID is required'})
        
        # Extract user email from JWT token claims
        user_email = None
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        claims = authorizer.get('claims', {})
        user_email = claims.get('email')
        
        if not user_email:
            logger.error("No email found in JWT claims")
            return create_response(401, {'error': 'Unauthorized'})
        
        # Initialize AWS clients
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
        
        logger.info(f"Deleted {deleted_count} DynamoDB records for user {user_email}, usecase {usecase_id}")
        
        # Update SNS filter policy to remove this usecase from the user's subscription
        logger.info(f"Calling remove_usecase_from_filter_policy for user {user_email}, usecase {usecase_id}")
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
    """
    Remove a usecase from the user's SNS filter policy.
    
    Args:
        sns_client: Boto3 SNS client
        email: User email address
        usecase_id_to_remove: Usecase ID to remove from filter
    """
    logger.info(f"=== Starting remove_usecase_from_filter_policy for email: {email}, usecase: {usecase_id_to_remove} ===")
    
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if not topic_arn:
        logger.info("SNS_TOPIC_ARN not set, skipping SNS filter policy update")
        return
    
    logger.info(f"Using SNS topic ARN: {topic_arn}")
    
    try:
        # Find the user's SNS subscription
        logger.info(f"Listing subscriptions for topic: {topic_arn}")
        response = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
        
        subscriptions = response.get('Subscriptions', [])
        logger.info(f"Found {len(subscriptions)} total subscriptions")
        
        subscription_arn = None
        for i, subscription in enumerate(subscriptions):
            endpoint = subscription.get('Endpoint')
            protocol = subscription.get('Protocol')
            arn = subscription.get('SubscriptionArn')
            
            logger.info(f"Subscription[{i}]: endpoint={endpoint}, protocol={protocol}, arn={arn}")
            
            if endpoint == email and protocol == 'email' and arn != 'PendingConfirmation':
                subscription_arn = arn
                logger.info(f"Found matching subscription for {email}: {subscription_arn}")
                break
        
        if not subscription_arn:
            logger.info(f"No confirmed SNS subscription found for {email}")
            return  # Not an error - user might not have SNS subscription
        
        # Get current filter policy from SNS subscription (ONLY source of truth)
        current_usecases = get_current_filter_policy_usecases(sns_client, subscription_arn)
        logger.info(f"Current SNS filter policy usecases for {email}: {current_usecases}, removing: {usecase_id_to_remove}")
        
        # Check if the usecase is actually in the current filter policy
        usecase_found = False
        logger.info(f"Looking for usecase '{usecase_id_to_remove}' (length: {len(usecase_id_to_remove)}) in current usecases:")
        for i, id in enumerate(current_usecases):
            match = id == usecase_id_to_remove
            logger.info(f"  [{i}] '{id}' (length: {len(id)}) - match: {match}")
            if match:
                usecase_found = True
                break
        
        if not usecase_found:
            logger.error(f"ERROR: Usecase '{usecase_id_to_remove}' not found in current filter policy {current_usecases} - nothing to remove")
            logger.error("This might be a case sensitivity or whitespace issue")
            return  # Nothing to do
        
        logger.info(f"SUCCESS: Found usecase '{usecase_id_to_remove}' in filter policy, proceeding with removal")
        
        # Remove the usecase we're unsubscribing from the current list
        filtered_usecases = [id for id in current_usecases if id != usecase_id_to_remove]
        removed_count = len(current_usecases) - len(filtered_usecases)
        logger.info(f"Removed {removed_count} instances of usecase {usecase_id_to_remove}")
        logger.info(f"Remaining usecases for {email}: {filtered_usecases}")
        
        # If no usecases left, unsubscribe completely
        if not filtered_usecases:
            logger.info(f"User {email} has no remaining usecase subscriptions, unsubscribing from SNS")
            sns_client.unsubscribe(SubscriptionArn=subscription_arn)
            logger.info(f"Successfully unsubscribed {email} from SNS topic")
            return
        
        # Update filter policy with remaining usecases
        filter_policy = create_filter_policy_json(filtered_usecases)
        logger.info(f"Updating filter policy for {email} with remaining usecases {filtered_usecases}: {filter_policy}")
        
        logger.info(f"About to call set_subscription_attributes with:")
        logger.info(f"  SubscriptionArn: {subscription_arn}")
        logger.info(f"  AttributeName: FilterPolicy")
        logger.info(f"  AttributeValue: {filter_policy}")
        
        sns_client.set_subscription_attributes(
            SubscriptionArn=subscription_arn,
            AttributeName='FilterPolicy',
            AttributeValue=filter_policy
        )
        
        logger.info("SUCCESS: set_subscription_attributes completed successfully")
        logger.info(f"Successfully updated filter policy for {email}: {filter_policy}")
        
        # Verify the update by reading the filter policy again
        logger.info("Verifying filter policy update...")
        verify_usecases = get_current_filter_policy_usecases(sns_client, subscription_arn)
        logger.info(f"Verified filter policy after update: {verify_usecases}")
        
    except Exception as e:
        logger.error(f"Error: Could not update SNS filter policy for {email}: {str(e)}", exc_info=True)
        # Continue anyway - don't fail the unsubscribe operation


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
        logger.error(f"Error: Could not parse filter policy JSON: {str(e)}")
        raise


def create_filter_policy_json(usecase_ids: List[str]) -> str:
    """
    Create the SNS filter policy JSON for multiple usecases.
    
    Args:
        usecase_ids: List of usecase IDs
        
    Returns:
        JSON string for SNS filter policy
    """
    return json.dumps({'usecase_id': usecase_ids})

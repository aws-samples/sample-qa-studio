import logging
import json
import os
from typing import Any, Dict, List, Optional
import boto3
from utils import get_table_name

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> None:
    """
    Lambda handler for sending notifications via Amazon SNS.
    Triggered by SQS messages containing notification requests.
    
    Args:
        event: SQS event with notification messages
        context: Lambda context
    """
    try:
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        sns_client = boto3.client('sns')
        
        # Process each SQS record
        for record in event.get('Records', []):
            try:
                # Parse notification message
                notification_msg = json.loads(record['Body'])
                usecase_id = notification_msg.get('usecaseId')
                execution_id = notification_msg.get('executionId')
                
                if not usecase_id or not execution_id:
                    logger.warning("Missing usecaseId or executionId in notification message")
                    continue
                
                # Get usecase details
                usecase = get_usecase(table, usecase_id)
                if not usecase:
                    logger.error(f"Usecase {usecase_id} not found")
                    continue
                
                # Get execution details
                execution = get_execution(table, usecase_id, execution_id)
                if not execution:
                    logger.error(f"Execution {execution_id} not found")
                    continue
                
                # Check if we should send notifications for this execution
                if not should_send_notification(execution):
                    logger.info(f"Skipping notification for execution (trigger type: {execution.get('trigger_type')}, status: {execution.get('status')})")
                    continue
                
                # Get subscribed users for this usecase
                subscriptions = get_user_subscriptions(table, usecase_id)
                if not subscriptions:
                    logger.info(f"No subscriptions found for usecase {usecase_id}")
                    continue
                
                # Send SNS notification with usecase_id filter attribute
                send_sns_notification_with_filter(sns_client, usecase, execution)
                logger.info(f"Successfully sent SNS notification for usecase {usecase.get('name')} to {len(subscriptions)} subscribers")
                
            except Exception as e:
                logger.error(f"Error processing notification record: {str(e)}", exc_info=True)
                continue
    
    except Exception as e:
        logger.error(f"Error in send_notification handler: {str(e)}", exc_info=True)


def should_send_notification(execution: Dict[str, Any]) -> bool:
    """
    Determine if we should send a notification based on execution details.
    
    Args:
        execution: Execution record from DynamoDB
        
    Returns:
        True if notification should be sent, False otherwise
    """
    # Send notifications for:
    # 1. Scheduled executions that failed
    # 2. Any execution that failed (optional - customize this logic)
    
    trigger_type = execution.get('trigger_type', '')
    status = execution.get('status', '')
    
    # For now, send notifications for failed scheduled executions
    if trigger_type == 'Scheduled' and status == 'error':
        return True
    
    return False


def get_usecase(table: Any, usecase_id: str) -> Optional[Dict[str, Any]]:
    """
    Get usecase details from DynamoDB.
    
    Args:
        table: DynamoDB table resource
        usecase_id: Usecase ID
        
    Returns:
        Usecase record or None if not found
    """
    try:
        response = table.get_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}'
            }
        )
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting usecase: {str(e)}")
        return None


def get_execution(table: Any, usecase_id: str, execution_id: str) -> Optional[Dict[str, Any]]:
    """
    Get execution details from DynamoDB.
    
    Args:
        table: DynamoDB table resource
        usecase_id: Usecase ID
        execution_id: Execution ID
        
    Returns:
        Execution record or None if not found
    """
    try:
        response = table.get_item(
            Key={
                'pk': f'USECASE_EXECUTION#{usecase_id}',
                'sk': f'EXECUTION#{execution_id}'
            }
        )
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting execution: {str(e)}")
        return None


def get_user_subscriptions(table: Any, usecase_id: str) -> List[Dict[str, Any]]:
    """
    Get all user subscriptions for a usecase.
    
    Args:
        table: DynamoDB table resource
        usecase_id: Usecase ID
        
    Returns:
        List of subscription records
    """
    try:
        from boto3.dynamodb.conditions import Key
        
        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('NOTIFICATION#')
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error getting user subscriptions: {str(e)}")
        return []


def send_sns_notification_with_filter(
    sns_client: Any,
    usecase: Dict[str, Any],
    execution: Dict[str, Any]
) -> None:
    """
    Send SNS notification with message filtering attributes.
    
    Args:
        sns_client: Boto3 SNS client
        usecase: Usecase record
        execution: Execution record
    """
    # Get SNS topic ARN from environment variable
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if not topic_arn:
        raise ValueError("SNS_TOPIC_ARN environment variable not set")
    
    # Get frontend URL from environment variable
    frontend_url = os.environ.get('FRONTEND_URL', 'https://your-app.com')
    
    # Create notification subject and status emoji based on execution status
    status = execution.get('status', '')
    usecase_name = usecase.get('name', 'Unknown')
    
    if status == 'COMPLETED':
        subject = f"✅ Execution Completed: {usecase_name}"
        status_emoji = "✅"
        status_message = "Your usecase execution completed successfully!"
    elif status in ['FAILED', 'ERROR']:
        subject = f"❌ Execution Failed: {usecase_name}"
        status_emoji = "❌"
        status_message = "Your usecase execution encountered an error and failed."
    else:
        subject = f"📋 Execution Update: {usecase_name}"
        status_emoji = "📋"
        status_message = f"Your usecase execution status: {status}"
    
    # Extract execution ID from SK
    execution_id = get_execution_id(execution.get('sk', ''))
    usecase_id = usecase.get('id', '')
    execution_link = f"{frontend_url}/usecase/{usecase_id}/execution/{execution_id}"
    
    # Create rich notification message
    message = f"""
{status_emoji} {usecase_name}

{status_message}

📋 EXECUTION DETAILS:
• Usecase: {usecase_name}
• Description: {usecase.get('description', '')}
• Execution ID: {execution_id}
• Status: {status} {status_emoji}
• Trigger Type: {execution.get('trigger_type', '')}
• Started At: {execution.get('created_at', '')}
• Completed At: {execution.get('completed_at', '')}
• Starting URL: {execution.get('starting_url', '')}

🔗 VIEW FULL DETAILS: {execution_link}

---
To manage your subscriptions, visit your dashboard.
    """
    
    # Create message attributes for SNS filtering
    message_attributes = {
        'usecase_id': {
            'DataType': 'String',
            'StringValue': usecase_id
        },
        'execution_status': {
            'DataType': 'String',
            'StringValue': status
        },
        'trigger_type': {
            'DataType': 'String',
            'StringValue': execution.get('trigger_type', '')
        }
    }
    
    # Publish to SNS topic with filter attributes
    try:
        response = sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message,
            MessageAttributes=message_attributes
        )
        
        message_id = response.get('MessageId')
        logger.info(f"Published SNS message {message_id} for usecase {usecase_name} with filter usecase_id={usecase_id}")
    except Exception as e:
        logger.error(f"Failed to publish SNS message: {str(e)}")
        raise


def get_execution_id(sk: str) -> str:
    """
    Extract execution ID from SK (removes "EXECUTION#" prefix).
    
    Args:
        sk: Sort key from DynamoDB
        
    Returns:
        Execution ID
    """
    if sk.startswith('EXECUTION#'):
        return sk[10:]
    return sk

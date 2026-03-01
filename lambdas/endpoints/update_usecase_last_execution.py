import logging
import json
from typing import Any, Dict
import boto3
from utils import get_table_name

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for CloudWatch Events to update usecase with last execution info.
    This is triggered by execution status change events.
    
    Args:
        event: CloudWatch Event
        context: Lambda context
        
    Returns:
        None (CloudWatch Event handler)
    """
    try:
        logger.info(f"Received event: {event.get('detail-type')} from source: {event.get('source')}")
        
        # Parse the event detail
        detail = event.get('detail', {})
        usecase_id = detail.get('usecase_id')
        execution_id = detail.get('execution_id')
        status = detail.get('status')
        timestamp = detail.get('timestamp')
        
        logger.info(f"Processing status change: usecase={usecase_id}, execution={execution_id}, status={status}")
        
        if not usecase_id or not execution_id or not status or not timestamp:
            logger.error("Missing required fields in event detail")
            return
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Update the usecase record with latest execution info.
        # Use ConditionExpression to prevent DynamoDB upsert from creating
        # ghost records when the usecase doesn't exist.
        try:
            table.update_item(
                Key={
                    'pk': 'USECASES',
                    'sk': f'USECASE#{usecase_id}'
                },
                UpdateExpression='SET last_execution_id = :exec_id, last_execution_status = :status, last_execution_time = :timestamp',
                ConditionExpression='attribute_exists(pk)',
                ExpressionAttributeValues={
                    ':exec_id': execution_id,
                    ':status': status,
                    ':timestamp': timestamp
                }
            )
            logger.info(f"Successfully updated usecase {usecase_id} with latest execution info")
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"Usecase {usecase_id} does not exist, skipping last execution update")
        
    except Exception as e:
        logger.error(f"Error updating usecase last execution: {str(e)}", exc_info=True)
        # Don't raise exception - CloudWatch Events doesn't need error response

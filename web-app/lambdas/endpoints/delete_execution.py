import logging
import json
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_bucket_name, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete an execution and its associated data.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with deletion result
    """
    # Validate scopes - deleting executions requires write permission
    user_identity, error = require_scopes(event, ['api/executions.write'])
    if error:
        return error
    
    try:
        # Get execution and usecase IDs from path
        execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
        if error:
            return error
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        s3_client = boto3.client('s3')
        
        # Delete Amazon S3 objects for this execution
        bucket_name = get_bucket_name()
        if bucket_name:
            try:
                delete_s3_objects(s3_client, bucket_name, usecase_id, execution_id)
            except Exception as e:
                logger.warning(f"Error deleting Amazon S3 objects: {str(e)}")
        
        # Delete execution
        try:
            table.delete_item(
                Key={
                    'pk': f'USECASE_EXECUTION#{usecase_id}',
                    'sk': f'EXECUTION#{execution_id}'
                }
            )
        except ClientError as e:
            logger.error(f"Error deleting execution: {str(e)}")
            return create_response(500, {'error': 'Failed to delete execution'})
        
        # Query and delete execution steps
        try:
            steps_response = table.query(
                KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & Key('sk').begins_with('EXECUTION_STEP#')
            )
            
            for item in steps_response.get('Items', []):
                try:
                    table.delete_item(
                        Key={
                            'pk': item['pk'],
                            'sk': item['sk']
                        }
                    )
                except ClientError as e:
                    logger.warning(f"Error deleting execution step: {str(e)}")
        except Exception as e:
            logger.error(f"Error querying execution steps: {str(e)}")
        
        logger.info(f"Successfully deleted execution {execution_id}")
        
        return create_response(200, {
            'status': 'execution deleted',
            'executionId': execution_id
        })
        
    except Exception as e:
        logger.error(f"Error deleting execution: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def delete_s3_objects(s3_client: Any, bucket_name: str, usecase_id: str, execution_id: str) -> None:
    """
    Delete all Amazon S3 objects for an execution.
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Amazon S3 bucket name
        usecase_id: Usecase ID
        execution_id: Execution ID
    """
    prefix = f"{usecase_id}/{execution_id}/"
    
    try:
        # List objects with execution prefix
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix
        )
        
        # Delete all objects
        for obj in response.get('Contents', []):
            try:
                s3_client.delete_object(
                    Bucket=bucket_name,
                    Key=obj['Key']
                )
            except ClientError as e:
                logger.warning(f"Error deleting Amazon S3 object {obj['Key']}: {str(e)}")
    except ClientError as e:
        logger.error(f"Error listing Amazon S3 objects: {str(e)}")
        raise

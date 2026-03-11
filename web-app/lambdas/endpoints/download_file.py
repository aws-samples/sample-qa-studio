import logging
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_bucket_name, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to generate a presigned URL for downloading a file.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with redirect to presigned URL
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/executions.read'])
        if error:
            return error
        
        # Get parameters from path
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
        if error:
            return error
        file_name = event.get('pathParameters', {}).get('fileName')
        
        logger.info(f"Generating download URL for UsecaseID: {usecase_id}, ExecutionID: {execution_id}, FileName: {file_name}")
        
        # Validate required fields
        if not file_name:
            return create_response(400, {'error': 'FileName is required'})
        
        # Initialize Amazon S3 client
        s3_client = boto3.client('s3')
        bucket_name = get_bucket_name()
        
        # Build Amazon S3 key
        s3_key = f"{usecase_id}/{execution_id}/downloads/{file_name}"
        logger.info(f"S3 Key: {s3_key}")
        
        # Check if file exists
        try:
            s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        except ClientError as e:
            logger.error(f"File not found: {str(e)}")
            return create_response(404, {'error': 'File not found'})
        
        # Generate presigned URL (1 hour expiration)
        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': s3_key},
                ExpiresIn=3600
            )
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return create_response(500, {'error': 'Failed to generate download URL'})
        
        logger.info(f"Redirecting to presigned URL: {presigned_url}")
        
        # Redirect to the presigned URL
        return {
            'statusCode': 302,
            'headers': {
                'Location': presigned_url,
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating download URL: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

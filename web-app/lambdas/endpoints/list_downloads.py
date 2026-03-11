import logging
from typing import Any, Dict, List
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_bucket_name, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list downloadable files for an execution.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of files
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
        
        logger.info(f"Listing downloads for UsecaseID: {usecase_id}, ExecutionID: {execution_id}")
        
        # Initialize Amazon S3 client
        s3_client = boto3.client('s3')
        bucket_name = get_bucket_name()
        
        # List objects in the downloads directory
        prefix = f"{usecase_id}/{execution_id}/downloads/"
        logger.info(f"Listing objects with prefix: {prefix}")
        
        try:
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix
            )
        except ClientError as e:
            logger.error(f"Error listing Amazon S3 objects: {str(e)}")
            return create_response(500, {'error': 'Failed to list downloads'})
        
        # Build response with file information
        files = []
        for obj in response.get('Contents', []):
            key = obj['Key']
            # Extract filename from key (remove prefix)
            filename = key[len(prefix):]
            
            # Skip if it's just the directory marker
            if not filename:
                continue
            
            files.append({
                'fileName': filename,
                'size': obj['Size'],
                'lastModified': obj['LastModified'].strftime('%Y-%m-%dT%H:%M:%SZ')
            })
        
        logger.info(f"Found {len(files)} files")
        
        return create_response(200, {'files': files})
        
    except Exception as e:
        logger.error(f"Error listing downloads: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})

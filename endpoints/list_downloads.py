import logging
from typing import Any, Dict, List
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_bucket_name

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
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        execution_id = path_params.get('executionId')
        
        logger.info(f"Listing downloads for UsecaseID: {usecase_id}, ExecutionID: {execution_id}")
        
        if not usecase_id or not execution_id:
            logger.error("UsecaseId and ExecutionId are required")
            return create_response(400, {'error': 'UsecaseId and ExecutionId are required'})
        
        # Initialize S3 client
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
            logger.error(f"Error listing S3 objects: {str(e)}")
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

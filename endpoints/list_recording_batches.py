import logging
from typing import Any, Dict
import json
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_bucket_name

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list recording batches for an execution.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of batch IDs and metadata
    """
    try:
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        execution_id = path_params.get('executionId')
        
        if not usecase_id or not execution_id:
            logger.error("UsecaseId and ExecutionId are required")
            return create_response(400, {'error': 'UsecaseId and ExecutionId are required'})
        
        # Initialize S3 client
        s3_client = boto3.client('s3')
        bucket_name = get_bucket_name()
        
        # New structure: /usecaseId/executionId/recording/{unknown_folder_id}/
        recording_base_prefix = f"{usecase_id}/{execution_id}/recording/"
        
        logger.info(f"Looking for recording folder in: s3://{bucket_name}/{recording_base_prefix}")
        
        # Find the actual recording folder
        recording_prefix = find_recording_folder(s3_client, bucket_name, recording_base_prefix)
        if not recording_prefix:
            logger.error("Recording folder not found")
            return create_response(404, {'error': 'Recording folder not found'})
        
        logger.info(f"Found recording at: s3://{bucket_name}/{recording_prefix}")
        
        # Load metadata
        metadata = load_metadata(s3_client, bucket_name, recording_prefix)
        
        # List batch files
        batch_ids = list_batch_files(s3_client, bucket_name, recording_prefix)
        
        if not batch_ids:
            logger.error("No batch files found in recording folder")
            return create_response(404, {'error': 'No recording batches found'})
        
        logger.info(f"Found {len(batch_ids)} batch files")
        
        return create_response(200, {
            'batches': batch_ids,
            'metadata': metadata
        })
        
    except Exception as e:
        logger.error(f"Error listing recording batches: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def find_recording_folder(s3_client, bucket: str, prefix: str) -> str:
    """
    Find the recording folder under the given prefix.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        prefix: Base prefix to search under
        
    Returns:
        Full prefix to the recording folder, or empty string if not found
    """
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            Delimiter='/',
            MaxKeys=10
        )
        
        common_prefixes = response.get('CommonPrefixes', [])
        if not common_prefixes:
            logger.error(f"No recording folder found under {prefix}")
            return ""
        
        folder_prefix = common_prefixes[0]['Prefix']
        logger.info(f"Found recording folder: {folder_prefix}")
        
        return folder_prefix
        
    except ClientError as e:
        logger.error(f"Error finding recording folder: {str(e)}")
        return ""


def load_metadata(s3_client, bucket: str, prefix: str) -> Dict[str, Any]:
    """
    Load metadata.json from the recording folder.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        prefix: Recording folder prefix
        
    Returns:
        Metadata dictionary, or empty dict if not found
    """
    try:
        metadata_key = f"{prefix.rstrip('/')}/metadata.json"
        
        response = s3_client.get_object(
            Bucket=bucket,
            Key=metadata_key
        )
        
        metadata = json.loads(response['Body'].read().decode('utf-8'))
        return metadata
        
    except ClientError as e:
        logger.warning(f"Could not load metadata: {str(e)}")
        return {}


def list_batch_files(s3_client, bucket: str, prefix: str) -> list:
    """
    List all batch files in the recording folder.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        prefix: Recording folder prefix
        
    Returns:
        Sorted list of batch IDs
    """
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=f"{prefix}batch_"
        )
        
        contents = response.get('Contents', [])
        if not contents:
            logger.error("No batch files found")
            return []
        
        # Extract batch IDs from filenames
        batch_ids = []
        for obj in contents:
            key = obj['Key']
            # Extract batch timestamp from "batch_1761741997665.ndjson.gz" -> "1761741997665"
            filename = key.split('/')[-1]
            if filename.startswith('batch_') and filename.endswith('.gz'):
                batch_id = filename.replace('batch_', '').replace('.gz', '').replace('.ndjson', '')
                batch_ids.append(batch_id)
        
        # Sort batch IDs
        batch_ids.sort()
        
        return batch_ids
        
    except ClientError as e:
        logger.error(f"Error listing batch files: {str(e)}")
        return []

import logging
import json
import gzip
from typing import Any, Dict, List
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_bucket_name

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get recording batch events with pagination.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with paginated events
    """
    try:
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        execution_id = path_params.get('executionId')
        batch_id = path_params.get('batchId')
        
        if not usecase_id or not execution_id or not batch_id:
            return create_response(400, {'error': 'UsecaseId, ExecutionId, and BatchId are required'})
        
        # Validate batchId format (should be 13 digit timestamp)
        if not is_valid_batch_id(batch_id):
            logger.error(f"Invalid batchId format: {batch_id}")
            return create_response(400, {'error': 'Invalid batchId format'})
        
        # Parse pagination parameters from query string
        query_params = event.get('queryStringParameters') or {}
        page = int(query_params.get('page', '1'))
        page_size = int(query_params.get('pageSize', '100'))
        
        # Validate pagination parameters
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 500:
            page_size = 100
        
        logger.info(f"Fetching batch {batch_id} with pagination: page={page}, pageSize={page_size}")
        
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
        
        # Load batch file
        batch_key = f"{recording_prefix}batch_{batch_id}.ndjson.gz"
        logger.info(f"Loading batch file: {batch_key}")
        
        all_events = load_batch_file(s3_client, bucket_name, batch_key)
        if all_events is None:
            logger.error("Batch file not found")
            return create_response(404, {'error': 'Batch file not found'})
        
        total_count = len(all_events)
        logger.info(f"Loaded {total_count} total events from batch {batch_id}")
        
        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        if start_idx >= total_count:
            start_idx = total_count
            end_idx = total_count
        elif end_idx > total_count:
            end_idx = total_count
        
        paginated_events = all_events[start_idx:end_idx]
        has_more = end_idx < total_count
        total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
        
        logger.info(f"Returning page {page}/{total_pages}: events {start_idx}-{end_idx} of {total_count} (hasMore={has_more})")
        
        return create_response(200, {
            'events': paginated_events,
            'totalCount': total_count,
            'totalPages': total_pages,
            'page': page,
            'pageSize': page_size,
            'hasMore': has_more
        })
        
    except Exception as e:
        logger.error(f"Error getting recording batch: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def is_valid_batch_id(batch_id: str) -> bool:
    """
    Validate batchId format (should be 13 digit timestamp).
    
    Args:
        batch_id: Batch ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    return len(batch_id) == 13 and batch_id.isdigit()


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


def load_batch_file(s3_client, bucket: str, key: str) -> List[Dict[str, Any]]:
    """
    Load and parse a batch file from S3.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        List of event dictionaries, or None if file not found
    """
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        
        # Decompress gzip
        with gzip.GzipFile(fileobj=response['Body']) as gzfile:
            content = gzfile.read().decode('utf-8')
        
        # Parse JSON lines
        batch_events = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            try:
                event = json.loads(line)
                
                # Validate event has required fields
                if 'type' not in event or 'timestamp' not in event:
                    continue
                
                batch_events.append(event)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Error parsing event line: {str(e)}")
                continue
        
        return batch_events
        
    except ClientError as e:
        logger.error(f"Error loading batch file: {str(e)}")
        return None

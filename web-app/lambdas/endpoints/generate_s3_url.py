import logging
import json
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_bucket_name

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Valid file extensions per mobile platform
PLATFORM_EXTENSIONS = {
    'ANDROID': '.apk',
    'IOS': '.ipa',
}


def _handle_app_binary(body: dict) -> Dict[str, Any]:
    """
    Handle app_binary file type: validate inputs, generate a pre-signed PUT URL,
    and store the S3 path on the Usecase DynamoDB record.
    """
    usecase_id = body.get('usecaseId', '')
    platform = body.get('platform', '')
    filename = body.get('filename', '')

    # Validate required fields
    if not usecase_id:
        return create_response(400, {'error': 'usecaseId is required for app_binary uploads'})
    if not platform:
        return create_response(400, {'error': 'platform is required for app_binary uploads'})
    if not filename:
        return create_response(400, {'error': 'filename is required for app_binary uploads'})

    # Validate platform value
    if platform not in PLATFORM_EXTENSIONS:
        return create_response(400, {
            'error': f'platform must be "ANDROID" or "IOS", got "{platform}"'
        })

    # Validate file extension matches platform
    expected_ext = PLATFORM_EXTENSIONS[platform]
    if not filename.lower().endswith(expected_ext):
        return create_response(400, {
            'error': f'File extension mismatch: {platform} requires {expected_ext} files, got "{filename}"'
        })

    # Build S3 key and generate pre-signed PUT URL
    s3_key = f"{usecase_id}/app_binary/{filename}"
    bucket_name = get_bucket_name()
    s3_client = boto3.client('s3', config=boto3.session.Config(signature_version='s3v4'))

    try:
        signed_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
            },
            ExpiresIn=3600,  # 1 hour expiration
        )
    except ClientError as e:
        logger.error(f"Error generating pre-signed PUT URL: {str(e)}")
        return create_response(500, {'error': 'Failed to generate upload URL'})

    # Store app_binary_s3_path on the Usecase DynamoDB record
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        table.update_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}',
            },
            UpdateExpression='SET #abs = :s3path',
            ExpressionAttributeNames={
                '#abs': 'app_binary_s3_path',
            },
            ExpressionAttributeValues={
                ':s3path': s3_key,
            },
        )
    except ClientError as e:
        logger.error(f"Error updating Usecase with app_binary_s3_path: {str(e)}")
        return create_response(500, {'error': 'Failed to store app binary path'})

    logger.info(f"Generated app_binary upload URL for usecase {usecase_id}, key={s3_key}")

    return create_response(200, {
        'signedUrl': signed_url,
        'fileName': filename,
        's3Key': s3_key,
    })


def _handle_browser_policy(body: dict) -> Dict[str, Any]:
    """
    Handle browser_policy file type: generate a pre-signed PUT URL
    and store the S3 path on the Usecase DynamoDB record.
    """
    usecase_id = body.get('usecaseId', '')
    filename = body.get('filename', '')

    if not usecase_id:
        return create_response(400, {'error': 'usecaseId is required for browser_policy uploads'})
    if not filename:
        return create_response(400, {'error': 'filename is required for browser_policy uploads'})
    if not filename.lower().endswith('.json'):
        return create_response(400, {'error': 'Browser policy file must be a .json file'})

    s3_key = f"{usecase_id}/browser_policy/{filename}"
    bucket_name = get_bucket_name()
    s3_client = boto3.client('s3', config=boto3.session.Config(signature_version='s3v4'))

    try:
        signed_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
                'ContentType': 'application/json',
            },
            ExpiresIn=3600,
        )
    except ClientError as e:
        logger.error(f"Error generating pre-signed PUT URL for browser policy: {str(e)}")
        return create_response(500, {'error': 'Failed to generate upload URL'})

    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        table.update_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}',
            },
            UpdateExpression='SET browser_policy_s3_path = :s3path',
            ExpressionAttributeValues={
                ':s3path': s3_key,
            },
        )
    except ClientError as e:
        logger.error(f"Error updating Usecase with browser_policy_s3_path: {str(e)}")
        return create_response(500, {'error': 'Failed to store browser policy path'})

    logger.info(f"Generated browser_policy upload URL for usecase {usecase_id}, key={s3_key}")

    return create_response(200, {
        'signedUrl': signed_url,
        'fileName': filename,
        's3Key': s3_key,
    })


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to generate pre-signed Amazon S3 URLs for execution artifacts
    and app binary uploads.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with signed URL
    """
    try:
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        file_type = body.get('fileType', 'html')

        # Validate fileType
        if file_type not in ['html', 'video', 'app_binary', 'browser_policy']:
            logger.error(f"Invalid fileType: {file_type}. Must be 'html', 'video', 'app_binary', or 'browser_policy'")
            return create_response(400, {'error': "fileType must be 'html', 'video', 'app_binary', or 'browser_policy'"})

        # Handle app_binary uploads (separate flow — no execution needed)
        if file_type == 'app_binary':
            return _handle_app_binary(body)

        # Handle browser_policy uploads
        if file_type == 'browser_policy':
            return _handle_browser_policy(body)

        # --- Existing artifact download flow (html / video) ---
        usecase_id = body.get('usecaseId', '')
        execution_id = body.get('executionId', '')
        act_id = body.get('actId', '')
        
        logger.info(f"UsecaseID: {usecase_id}, ExecutionID: {execution_id}, ActID: {act_id}")
        
        # Validate required fields
        if not usecase_id or not execution_id:
            logger.error("UsecaseId and ExecutionId are required")
            return create_response(400, {'error': 'UsecaseId and ExecutionId are required'})
        
        # ActId is only required for HTML files
        if file_type == 'html' and not act_id:
            logger.error("ActId is required for HTML files")
            return create_response(400, {'error': 'ActId is required for HTML files'})
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Load execution to get the Nova Act session ID
        response = table.get_item(
            Key={
                'pk': f'USECASE_EXECUTION#{usecase_id}',
                'sk': f'EXECUTION#{execution_id}'
            }
        )
        
        if 'Item' not in response:
            logger.error(f"Execution not found: {usecase_id}/{execution_id}")
            return create_response(404, {'error': 'Execution not found'})
        
        execution = response['Item']
        
        # Check if we have a Nova Act session ID
        nova_session_id = execution.get('nova_session_id', '')
        if not nova_session_id:
            logger.error(f"No Nova Act session ID found for execution: {execution_id}")
            return create_response(404, {'error': 'Nova Act session not found'})
        
        # Create S3 client
        s3_client = boto3.client('s3')
        bucket_name = get_bucket_name()
        
        # Determine the prefix based on file type
        if file_type == 'video':
            # Video files are in the recording folder
            # Structure: {usecase_id}/{execution_id}/recording/{session_folder}/
            recording_base_prefix = f"{usecase_id}/{execution_id}/recording/"
            
            logger.info(f"Looking for video in recording folder: {recording_base_prefix}")
            
            # Find the actual recording folder (there's a subfolder with the session ID)
            try:
                list_response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    Prefix=recording_base_prefix,
                    Delimiter='/'
                )
                
                common_prefixes = list_response.get('CommonPrefixes', [])
                if not common_prefixes:
                    logger.error(f"No recording folder found under {recording_base_prefix}")
                    return create_response(404, {'error': 'Recording folder not found'})
                
                # Use the first (and should be only) subfolder
                prefix = common_prefixes[0]['Prefix']
                logger.info(f"Found recording folder: {prefix}")
                
            except ClientError as e:
                logger.error(f"Error finding recording folder: {str(e)}")
                return create_response(500, {'error': 'Failed to find recording folder'})
        else:
            # HTML files are stored directly under the session ID
            prefix = f"{usecase_id}/{execution_id}/{nova_session_id}/"
        
        logger.info(f"Using prefix: {prefix}")
        
        # List objects in S3
        try:
            list_response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix
            )
        except ClientError as e:
            logger.error(f"Error listing Amazon S3 objects: {str(e)}")
            return create_response(500, {'error': 'Failed to list S3 objects'})
        
        # Find the file based on type
        found_key = None
        file_name = None
        content_type = None
        
        if file_type == 'html':
            # Find HTML file matching pattern: act_{act_id}_{wildcard}.html
            file_prefix = f"{prefix}act_{act_id}_"
            logger.info(f"HTML filePrefix: {file_prefix}")
            
            for obj in list_response.get('Contents', []):
                key = obj['Key']
                logger.info(f"obj.Key: {key}")
                if key.startswith(file_prefix) and key.endswith('.html'):
                    found_key = key
                    file_name = key.replace(prefix, '', 1)
                    content_type = 'text/html'
                    logger.info(f"Found matching HTML file: {found_key}")
                    break
        
        elif file_type == 'video':
            # Find video file matching pattern: {session_id}.webm
            logger.info("Looking for video file: .webm")
            
            for obj in list_response.get('Contents', []):
                key = obj['Key']
                logger.info(f"Checking video obj.Key: {key}")
                if key.endswith('.webm'):
                    found_key = key
                    file_name = f"{nova_session_id}.webm"
                    content_type = 'video/webm'
                    logger.info(f"Found matching video file: {found_key}")
                    break
        
        if not found_key:
            logger.error(f"No {file_type} file found for act_id: {act_id}")
            return create_response(404, {'error': f'{file_type} file not found'})
        
        # Generate pre-signed URL for the found file with appropriate content type
        try:
            signed_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': found_key,
                    'ResponseContentType': content_type
                },
                ExpiresIn=3600  # 1 hour expiration
            )
        except ClientError as e:
            logger.error(f"Error generating pre-signed URL: {str(e)}")
            return create_response(500, {'error': 'Failed to generate pre-signed URL'})
        
        return create_response(200, {
            'signedUrl': signed_url,
            'fileName': file_name
        })
        
    except Exception as e:
        logger.error(f"Error generating S3 URL: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
"""
Cache Builder Lambda

Event-driven Lambda function that automatically builds step caches from Nova Act
responses after successful test executions. Processes EventBridge events, fetches
Nova Act response files from S3, parses them using cache_parser module, and updates
STEP records in DynamoDB with cached actions.

This enables 40-60% faster test execution by replaying cached steps via Playwright
instead of calling Nova Act.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from worker.cache_parser import parse_nova_act_steps

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def check_cache_eligibility(table, usecase_id: str) -> bool:
    """
    Verify if caching is enabled for the usecase.
    
    Queries the USECASE record and checks the enable_cache field. Handles
    missing records gracefully by logging and returning False.
    
    Args:
        table: DynamoDB table resource
        usecase_id: Usecase identifier
        
    Returns:
        True if enable_cache is True, False otherwise
    """
    try:
        response = table.get_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}'
            }
        )
        
        # Check if USECASE record exists
        if 'Item' not in response:
            logger.error(f"USECASE record not found for usecase_id={usecase_id}")
            return False
        
        usecase = response['Item']
        enable_cache = usecase.get('enable_cache', False)
        
        if not enable_cache:
            logger.info(f"Cache disabled for usecase_id={usecase_id}: enable_cache={enable_cache}")
            return False
        
        logger.info(f"Cache enabled for usecase_id={usecase_id}")
        return True
        
    except ClientError as e:
        logger.error(f"DynamoDB error checking cache eligibility for usecase_id={usecase_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking cache eligibility for usecase_id={usecase_id}: {e}", exc_info=True)
        return False
def discover_act_files(s3_client, bucket: str, usecase_id: str, execution_id: str) -> Dict[str, str]:
    """
    List S3 act files and build act_id to s3_key mapping.

    Lists S3 objects with prefix {usecase_id}/{execution_id}/ and extracts
    act_id from each key using regex pattern act_(.+)\\.json. Handles empty
    results and S3 access errors gracefully with logging.

    Note: Nova Act stores artifacts at {usecase_id}/{execution_id}/{session_id}/act_*.json
    but we list at the execution level to find all session artifacts.

    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        usecase_id: Usecase identifier
        execution_id: Execution identifier

    Returns:
        Dictionary mapping {act_id: s3_key}
    """
    act_mapping = {}
    prefix = f'{usecase_id}/{execution_id}/'

    try:
        logger.info(f"Listing S3 objects with prefix={prefix} in bucket={bucket}")

        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix
        )

        # Check if any objects were found
        if 'Contents' not in response:
            logger.warning(f"No S3 act files found for usecase={usecase_id}, execution={execution_id}")
            return act_mapping

        # Parse act_id from each S3 key
        pattern = re.compile(r'.*/act_(.+)\.json$')
        for obj in response['Contents']:
            s3_key = obj['Key']
            match = pattern.match(s3_key)

            if match:
                act_id = match.group(1)
                act_mapping[act_id] = s3_key
                logger.debug(f"Mapped act_id={act_id} to s3_key={s3_key}")
            else:
                logger.warning(f"S3 key does not match expected pattern: {s3_key}")

        logger.info(f"Found {len(act_mapping)} act files for usecase={usecase_id}, execution={execution_id}")
        return act_mapping

    except ClientError as e:
        logger.error(f"S3 access error listing act files for usecase={usecase_id}, execution={execution_id}: {e}", exc_info=True)
        return act_mapping
    except Exception as e:
        logger.error(f"Unexpected error listing act files for usecase={usecase_id}, execution={execution_id}: {e}", exc_info=True)
        return act_mapping


def get_execution_steps(table, execution_id: str) -> list:
    """
    Query EXECUTION_STEP records for the execution.
    
    Queries DynamoDB for all EXECUTION_STEP records belonging to the specified
    execution. Handles DynamoDB errors gracefully by logging and returning an
    empty list.
    
    Args:
        table: DynamoDB table resource
        execution_id: Execution identifier
        
    Returns:
        List of EXECUTION_STEP records
    """
    try:
        from boto3.dynamodb.conditions import Key
        
        logger.info(f"Querying EXECUTION_STEP records for execution_id={execution_id}")
        
        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & 
                                  Key('sk').begins_with('EXECUTION_STEP#')
        )
        
        items = response.get('Items', [])
        logger.info(f"Found {len(items)} EXECUTION_STEP records for execution_id={execution_id}")
        
        return items
        
    except ClientError as e:
        logger.error(f"DynamoDB error querying execution steps for execution_id={execution_id}: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error querying execution steps for execution_id={execution_id}: {e}", exc_info=True)
        return []





def filter_navigation_steps(steps: list, act_mapping: Dict[str, str]) -> list:
    """
    Filter steps to only navigation steps with matching act files.
    
    Filters EXECUTION_STEP records to only include steps where:
    - step_type equals "navigation"
    - act_id field exists and is not None
    - act_id exists in the act_mapping dictionary
    
    Logs the count of navigation steps found and steps with matching act files
    for observability.
    
    Args:
        steps: List of EXECUTION_STEP records
        act_mapping: Dictionary mapping act_id to s3_key
        
    Returns:
        Filtered list of navigation steps with act files
    """
    # Count all navigation steps
    navigation_steps = [
        step for step in steps
        if step.get('step_type') == 'navigation'
    ]
    
    logger.info(f"Found {len(navigation_steps)} navigation steps out of {len(steps)} total steps")
    
    # Filter to only navigation steps with valid act_id in mapping
    filtered_steps = [
        step for step in navigation_steps
        if step.get('act_id') and step.get('act_id') in act_mapping
    ]
    
    logger.info(f"Found {len(filtered_steps)} navigation steps with matching act files")
    
    # Log skipped steps for observability
    skipped_count = len(navigation_steps) - len(filtered_steps)
    if skipped_count > 0:
        logger.warning(f"Skipped {skipped_count} navigation steps due to missing or unmatched act_id")
    
    return filtered_steps


def fetch_and_parse_act_response(s3_client, bucket: str, s3_key: str) -> Optional[List[Dict]]:
    """
    Fetch Nova Act response from S3 and parse it into cacheable steps.
    
    Fetches the Nova Act response JSON from S3 using get_object, then invokes
    parse_nova_act_steps() from the cache_parser module to extract cacheable
    actions. Handles S3 fetch errors and parsing exceptions gracefully with
    logging.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        s3_key: S3 object key for the act file
        
    Returns:
        List of parsed cached steps, or None if fetching/parsing fails
        
    Example:
        >>> s3_client = boto3.client('s3')
        >>> cached_steps = fetch_and_parse_act_response(
        ...     s3_client, 'my-bucket', 'executions/exec_123/act_act_456.json'
        ... )
        >>> # Returns: [{'type': 'click', 'bbox': {...}}, ...]
    """
    try:
        logger.debug(f"Fetching act file from S3: bucket={bucket}, key={s3_key}")
        
        # Fetch Nova Act response from S3
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        act_response_json = response['Body'].read().decode('utf-8')
        act_response = json.loads(act_response_json)
        
        logger.debug(f"Successfully fetched act file: {s3_key}")
        
        # Parse Nova Act response using cache_parser module
        cached_steps = parse_nova_act_steps(act_response)
        
        if cached_steps is None or len(cached_steps) == 0:
            logger.warning(f"No cacheable actions found in act file: {s3_key}")
            return None
        
        logger.info(f"Successfully parsed {len(cached_steps)} cacheable actions from {s3_key}")
        return cached_steps
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        logger.error(
            f"S3 error fetching act file {s3_key}: {error_code} - {str(e)}",
            exc_info=True
        )
        return None
        
    except json.JSONDecodeError as e:
        logger.error(
            f"JSON decode error parsing act file {s3_key}: {str(e)}",
            exc_info=True
        )
        return None
        
    except Exception as e:
        logger.error(
            f"Unexpected error fetching/parsing act file {s3_key}: {str(e)}",
            exc_info=True
        )
        return None


def update_step_caches(
    table,
    usecase_id: str,
    step_updates: List[tuple],
    timestamp: str
) -> tuple:
    """
    Update STEP records with cached steps using batch_writer.

    Uses DynamoDB batch_writer for efficient batch updates of STEP records.
    Each step update contains (step_id, cached_steps) tuple. Stores cached_steps
    as JSON string and cache_last_updated timestamp. Tracks successful and failed
    updates, handling errors gracefully by logging and continuing.

    Args:
        table: DynamoDB table resource
        usecase_id: Usecase identifier
        step_updates: List of tuples containing (step_id, cached_steps) pairs
        timestamp: Cache update timestamp (ISO 8601 format)

    Returns:
        Tuple of (successful_updates, failed_updates)

    Example:
        >>> table = dynamodb.Table('qa-studio-table')
        >>> step_updates = [
        ...     ('step_1', [{'type': 'click', 'bbox': {...}}]),
        ...     ('step_2', [{'type': 'type', 'text': 'hello'}])
        ... ]
        >>> successful, failed = update_step_caches(
        ...     table, 'uc_123', step_updates, '2024-01-01T12:00:00.000Z'
        ... )
        >>> print(f"Success: {successful}, Failed: {failed}")
    """
    successful = 0
    failed = 0

    logger.info(f"Starting batch update of {len(step_updates)} STEP records for usecase_id={usecase_id}")

    try:
        with table.batch_writer() as batch:
            for step_id, cached_steps in step_updates:
                try:
                    # Validate step_id
                    if not step_id:
                        logger.error(f"Missing step_id in update, skipping")
                        failed += 1
                        continue

                    # Serialize cached_steps to JSON string
                    cached_steps_json = json.dumps(cached_steps)

                    # Construct STEP record key and update
                    item = {
                        'pk': f'USECASE#{usecase_id}',
                        'sk': f'STEP#{step_id}',
                        'cached_steps': cached_steps_json,
                        'cache_last_updated': timestamp
                    }

                    batch.put_item(Item=item)
                    successful += 1
                    logger.debug(f"Queued cache update for step_id={step_id}")

                except TypeError as e:
                    # JSON encoding errors raise TypeError
                    logger.error(
                        f"JSON encoding error for step_id={step_id}: {str(e)}",
                        exc_info=True
                    )
                    failed += 1

                except Exception as e:
                    logger.error(
                        f"Error updating cache for step_id={step_id}: {str(e)}",
                        exc_info=True
                    )
                    failed += 1

        logger.info(
            f"Batch update completed: {successful} successful, {failed} failed "
            f"for usecase_id={usecase_id}"
        )

    except ClientError as e:
        logger.error(
            f"DynamoDB batch_writer error for usecase_id={usecase_id}: {str(e)}",
            exc_info=True
        )
        # If batch_writer itself fails, count all as failed
        failed = len(step_updates)
        successful = 0

    except Exception as e:
        logger.error(
            f"Unexpected error in batch update for usecase_id={usecase_id}: {str(e)}",
            exc_info=True
        )
        # If unexpected error, count all as failed
        failed = len(step_updates)
        successful = 0

    return (successful, failed)



def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for cache building triggered by EventBridge.
    
    Processes usecase.execution.completed events and builds step caches from
    Nova Act responses. Uses fire-and-forget error handling where all errors
    are caught and logged but never raised to Lambda runtime.
    
    Implements step-level error isolation where individual step failures do not
    prevent processing of remaining steps. Tracks and returns statistics for
    observability.
    
    Args:
        event: EventBridge event with detail containing usecase_id, execution_id,
               execution_status, and timestamp
        context: Lambda context
        
    Returns:
        Dict with statusCode 200 and body containing processing statistics
    """
    try:
        logger.info(f"Received cache builder event: {event.get('detail-type')}")
        
        # Extract event details
        detail = event.get('detail', {})
        usecase_id = detail.get('usecase_id')
        execution_id = detail.get('execution_id')
        execution_status = detail.get('execution_status')
        timestamp = detail.get('timestamp')
        
        # Validate required fields
        if not all([usecase_id, execution_id, execution_status, timestamp]):
            logger.error(f"Missing required event fields: {detail}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Missing required event fields',
                    'stats': {
                        'steps_processed': 0,
                        'successful_updates': 0,
                        'failed_updates': 0
                    }
                })
            }
        
        logger.info(f"Processing cache build for usecase={usecase_id}, execution={execution_id}, status={execution_status}")
        
        # Skip non-success executions
        if execution_status != 'success':
            logger.info(f"Skipping cache build: execution status is '{execution_status}', not 'success'")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Skipped: execution status is {execution_status}',
                    'stats': {
                        'steps_processed': 0,
                        'successful_updates': 0,
                        'failed_updates': 0
                    }
                })
            }
        
        # Get environment variables
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')
        s3_bucket = os.environ.get('S3_BUCKET')
        
        if not table_name or not s3_bucket:
            logger.error(f"Missing environment variables: DYNAMODB_TABLE_NAME={table_name}, S3_BUCKET={s3_bucket}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Missing environment variables',
                    'stats': {
                        'steps_processed': 0,
                        'successful_updates': 0,
                        'failed_updates': 0
                    }
                })
            }
        
        logger.info(f"Using table={table_name}, bucket={s3_bucket}")
        
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        s3_client = boto3.client('s3')
        
        # Check cache eligibility
        if not check_cache_eligibility(table, usecase_id):
            logger.info(f"Skipping cache build: cache not enabled or usecase not found for usecase_id={usecase_id}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Skipped: cache not enabled or usecase not found',
                    'stats': {
                        'steps_processed': 0,
                        'successful_updates': 0,
                        'failed_updates': 0
                    }
                })
            }
        
        # Discover act files in S3
        act_mapping = discover_act_files(s3_client, s3_bucket, usecase_id, execution_id)
        
        if not act_mapping:
            logger.warning(f"No act files found for execution_id={execution_id}, skipping cache build")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No act files found',
                    'stats': {
                        'steps_processed': 0,
                        'successful_updates': 0,
                        'failed_updates': 0
                    }
                })
            }
        
        # Get execution steps from DynamoDB
        execution_steps = get_execution_steps(table, execution_id)
        
        if not execution_steps:
            logger.warning(f"No execution steps found for execution_id={execution_id}, skipping cache build")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No execution steps found',
                    'stats': {
                        'steps_processed': 0,
                        'successful_updates': 0,
                        'failed_updates': 0
                    }
                })
            }
        
        # Filter to navigation steps with matching act files
        filtered_steps = filter_navigation_steps(execution_steps, act_mapping)
        
        if not filtered_steps:
            logger.warning(f"No navigation steps with act files found for execution_id={execution_id}, skipping cache build")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No navigation steps with act files found',
                    'stats': {
                        'steps_processed': 0,
                        'successful_updates': 0,
                        'failed_updates': 0
                    }
                })
            }
        
        # Process each filtered step with step-level error isolation
        step_updates = []
        steps_processed = 0
        
        for step in filtered_steps:
            try:
                steps_processed += 1
                
                # Extract step_id field (Task 6.1 requirement)
                step_id = step.get('step_id')
                
                if not step_id:
                    logger.error(f"Missing step_id field in EXECUTION_STEP record: {step.get('sk')}, skipping step")
                    continue
                
                # Get act_id and corresponding S3 key
                act_id = step.get('act_id')
                s3_key = act_mapping.get(act_id)
                
                if not s3_key:
                    logger.warning(f"No S3 key found for act_id={act_id}, step_id={step_id}, skipping step")
                    continue
                
                # Fetch and parse act response
                cached_steps = fetch_and_parse_act_response(s3_client, s3_bucket, s3_key)
                
                if cached_steps is None:
                    logger.warning(f"Failed to parse act response for step_id={step_id}, act_id={act_id}, skipping step")
                    continue
                
                # Add to update list (step_id, cached_steps)
                step_updates.append((step_id, cached_steps))
                logger.debug(f"Prepared cache update for step_id={step_id} with {len(cached_steps)} cached actions")
                
            except Exception as e:
                # Step-level error isolation: log error and continue with next step
                logger.error(
                    f"Error processing step {step.get('sk')}: {str(e)}",
                    exc_info=True
                )
                continue
        
        # Update step caches in batch
        successful_updates = 0
        failed_updates = 0
        
        if step_updates:
            logger.info(f"Updating {len(step_updates)} STEP records with cached steps")
            successful_updates, failed_updates = update_step_caches(
                table, usecase_id, step_updates, timestamp
            )
        else:
            logger.warning(f"No step updates to perform for execution_id={execution_id}")
        
        # Log summary statistics
        logger.info(
            f"Cache building completed for usecase={usecase_id}, execution={execution_id}: "
            f"processed={steps_processed}, successful={successful_updates}, failed={failed_updates}"
        )
        
        # Return success response with statistics
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Cache building completed',
                'stats': {
                    'steps_processed': steps_processed,
                    'successful_updates': successful_updates,
                    'failed_updates': failed_updates
                }
            })
        }
        
    except Exception as e:
        # Fire-and-forget: catch all exceptions, log, and return success
        logger.error(f"Error in cache builder lambda: {str(e)}", exc_info=True)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Cache building failed with error',
                'error': str(e),
                'stats': {
                    'steps_processed': 0,
                    'successful_updates': 0,
                    'failed_updates': 0
                }
            })
        }

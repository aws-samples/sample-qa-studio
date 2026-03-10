"""
AWS Lambda function to clean up AWS Backup recovery points before vault deletion.
This function is triggered as a CloudFormation custom resource during stack deletion.
"""
import json
import logging
import time
import boto3
from typing import Dict, Any, List
import urllib3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Amazon DynamoDB client
backup_client = boto3.client('backup')
http = urllib3.PoolManager()

# Constants
MAX_WAIT_TIME = 600  # 10 minutes maximum wait time
POLL_INTERVAL = 10   # Check every 10 seconds


def send_response(event: Dict[str, Any], context: Any, response_status: str, 
                  response_data: Dict[str, Any], physical_resource_id: str = None,
                  reason: str = None) -> None:
    """
    Send response to CloudFormation custom resource.
    
    Args:
        event: CloudFormation event
        context: Lambda context
        response_status: SUCCESS or FAILED
        response_data: Data to return to CloudFormation
        physical_resource_id: Physical resource ID
        reason: Reason for failure (if applicable)
    """
    response_url = event.get('ResponseURL')
    if not response_url:
        logger.warning("No ResponseURL in event, skipping CloudFormation response")
        return
    
    response_body = {
        'Status': response_status,
        'Reason': reason or f'See CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }
    
    json_response_body = json.dumps(response_body)
    
    logger.info(f"Response body: {json_response_body}")
    
    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }
    
    try:
        response = http.request(
            'PUT',
            response_url,
            body=json_response_body,
            headers=headers
        )
        logger.info(f"CloudFormation response status: {response.status}")
    except Exception as e:
        logger.error(f"Failed to send response to CloudFormation: {str(e)}")


def list_recovery_points(vault_name: str) -> List[str]:
    """
    List all recovery points in a backup vault.
    
    Args:
        vault_name: Name of the backup vault
        
    Returns:
        List of recovery point ARNs
    """
    recovery_points = []
    next_token = None
    
    try:
        while True:
            if next_token:
                response = backup_client.list_recovery_points_by_backup_vault(
                    BackupVaultName=vault_name,
                    NextToken=next_token
                )
            else:
                response = backup_client.list_recovery_points_by_backup_vault(
                    BackupVaultName=vault_name
                )
            
            for recovery_point in response.get('RecoveryPoints', []):
                recovery_points.append(recovery_point['RecoveryPointArn'])
            
            next_token = response.get('NextToken')
            if not next_token:
                break
        
        logger.info(f"Found {len(recovery_points)} recovery points in vault {vault_name}")
        return recovery_points
        
    except backup_client.exceptions.ResourceNotFoundException:
        logger.info(f"Backup vault {vault_name} not found")
        return []
    except Exception as e:
        logger.error(f"Error listing recovery points: {str(e)}")
        raise


def delete_recovery_point(vault_name: str, recovery_point_arn: str) -> bool:
    """
    Delete a single recovery point.
    
    Args:
        vault_name: Name of the backup vault
        recovery_point_arn: ARN of the recovery point to delete
        
    Returns:
        True if deletion was initiated successfully
    """
    try:
        backup_client.delete_recovery_point(
            BackupVaultName=vault_name,
            RecoveryPointArn=recovery_point_arn
        )
        logger.info(f"Initiated deletion of recovery point: {recovery_point_arn}")
        return True
    except backup_client.exceptions.ResourceNotFoundException:
        logger.info(f"Recovery point already deleted: {recovery_point_arn}")
        return True
    except Exception as e:
        logger.error(f"Error deleting recovery point {recovery_point_arn}: {str(e)}")
        return False


def wait_for_deletions(vault_name: str, max_wait_time: int = MAX_WAIT_TIME) -> bool:
    """
    Wait for all recovery points to be deleted.
    
    Args:
        vault_name: Name of the backup vault
        max_wait_time: Maximum time to wait in seconds
        
    Returns:
        True if all recovery points are deleted, False if timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            recovery_points = list_recovery_points(vault_name)
            
            if not recovery_points:
                logger.info("All recovery points have been deleted")
                return True
            
            logger.info(f"Still waiting for {len(recovery_points)} recovery points to be deleted...")
            time.sleep(POLL_INTERVAL)
            
        except Exception as e:
            logger.error(f"Error checking recovery point status: {str(e)}")
            time.sleep(POLL_INTERVAL)
    
    logger.warning(f"Timeout waiting for recovery points to be deleted after {max_wait_time} seconds")
    return False


def cleanup_backup_vault(vault_name: str) -> Dict[str, Any]:
    """
    Clean up all recovery points in a backup vault.
    
    Args:
        vault_name: Name of the backup vault
        
    Returns:
        Dictionary with cleanup results
    """
    logger.info(f"Starting cleanup of backup vault: {vault_name}")
    
    # List all recovery points
    recovery_points = list_recovery_points(vault_name)
    
    if not recovery_points:
        logger.info("No recovery points to delete")
        return {
            'RecoveryPointsDeleted': 0,
            'Status': 'Success',
            'Message': 'No recovery points found'
        }
    
    # Delete all recovery points
    deleted_count = 0
    failed_count = 0
    
    for recovery_point_arn in recovery_points:
        if delete_recovery_point(vault_name, recovery_point_arn):
            deleted_count += 1
        else:
            failed_count += 1
    
    logger.info(f"Initiated deletion of {deleted_count} recovery points, {failed_count} failed")
    
    # Wait for deletions to complete
    if deleted_count > 0:
        logger.info("Waiting for recovery point deletions to complete...")
        all_deleted = wait_for_deletions(vault_name)
        
        if not all_deleted:
            return {
                'RecoveryPointsDeleted': deleted_count,
                'Status': 'Partial',
                'Message': f'Deletion initiated for {deleted_count} recovery points but not all completed within timeout'
            }
    
    return {
        'RecoveryPointsDeleted': deleted_count,
        'Status': 'Success',
        'Message': f'Successfully deleted {deleted_count} recovery points'
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for CloudFormation custom resource.
    
    Args:
        event: CloudFormation event
        context: Lambda context
        
    Returns:
        Response dictionary
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    request_type = event.get('RequestType')
    resource_properties = event.get('ResourceProperties', {})
    vault_name = resource_properties.get('BackupVaultName')
    
    try:
        # Only clean up on Delete events
        if request_type == 'Delete':
            if not vault_name:
                raise ValueError("BackupVaultName is required")
            
            logger.info(f"Processing DELETE request for vault: {vault_name}")
            result = cleanup_backup_vault(vault_name)
            
            send_response(
                event, 
                context, 
                'SUCCESS', 
                result,
                physical_resource_id=f"BackupVaultCleanup-{vault_name}"
            )
            
            return result
        
        elif request_type in ['Create', 'Update']:
            # No action needed on Create or Update
            logger.info(f"Processing {request_type} request - no action needed")
            send_response(
                event,
                context,
                'SUCCESS',
                {'Message': f'{request_type} completed - no action taken'},
                physical_resource_id=f"BackupVaultCleanup-{vault_name or 'unknown'}"
            )
            
            return {'Status': 'Success', 'Message': f'{request_type} completed'}
        
        else:
            raise ValueError(f"Unknown request type: {request_type}")
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        send_response(
            event,
            context,
            'FAILED',
            {},
            reason=str(e)
        )
        raise

"""
Nova Act Workflow Definition Management

This module handles the creation and management of Nova Act workflow definitions
in the us-east-1 region for the GA service.
"""

import os
import logging
import boto3

logger = logging.getLogger(__name__)

NOVA_ACT_REGION = 'us-east-1'


def ensure_workflow_definition(usecase_id: str) -> str:
    """
    Ensure Nova Act workflow definition exists, create if needed.
    
    Args:
        usecase_id: The usecase ID to create a workflow for
        
    Returns:
        str: The sanitized workflow definition name
        
    Raises:
        ValueError: If NOVA_ACT_S3_BUCKET environment variable is not set
        Exception: If workflow creation fails
    """
    # Workflow names: 1-40 chars, a-z A-Z 0-9 - _, no spaces
    # Use usecase_id directly as workflow name
    # Sanitize: keep only valid characters
    workflow_name = ''.join(c if c.isalnum() or c in '-_' else '-' for c in usecase_id)
    
    # Ensure max 40 chars
    if len(workflow_name) > 40:
        workflow_name = workflow_name[:40]
    
    s3_bucket = os.getenv('NOVA_ACT_S3_BUCKET')
    if not s3_bucket:
        logger.error("NOVA_ACT_S3_BUCKET environment variable not set")
        raise ValueError("NOVA_ACT_S3_BUCKET is required for Nova Act GA service")
    
    try:
        # Use nova-act client for workflow management
        client = boto3.client('nova-act', region_name=NOVA_ACT_REGION)
        
        # Check if workflow definition exists
        try:
            response = client.get_workflow_definition(workflowDefinitionName=workflow_name)
            logger.info(f"Workflow definition '{workflow_name}' already exists (ID: {response.get('id', 'unknown')})")
        except client.exceptions.ResourceNotFoundException:
            # Create workflow definition
            logger.info(f"Creating Nova Act workflow definition '{workflow_name}' with S3 bucket '{s3_bucket}'")
            response = client.create_workflow_definition(
                name=workflow_name,
                description=f"Nova Act workflow for usecase {usecase_id}",
                exportConfig={
                    's3BucketName': s3_bucket
                }
            )
            logger.info(f"Created workflow definition '{workflow_name}' (ID: {response.get('id', 'unknown')})")
        except Exception as e:
            logger.warning(f"Could not check workflow definition: {e}. Will attempt to use it anyway.")
            
    except Exception as e:
        logger.error(f"Error ensuring workflow definition: {e}")
        raise
    
    return workflow_name


def delete_workflow_definition(usecase_id: str) -> bool:
    """
    Delete Nova Act workflow definition for a usecase.
    
    Args:
        usecase_id: The usecase ID whose workflow should be deleted
        
    Returns:
        bool: True if deleted successfully or didn't exist, False on error
    """
    # Sanitize workflow name same way as creation
    workflow_name = ''.join(c if c.isalnum() or c in '-_' else '-' for c in usecase_id)
    if len(workflow_name) > 40:
        workflow_name = workflow_name[:40]
    
    try:
        client = boto3.client('nova-act', region_name=NOVA_ACT_REGION)
        
        # Try to delete the workflow definition
        try:
            client.delete_workflow_definition(workflowDefinitionName=workflow_name)
            logger.info(f"Deleted workflow definition '{workflow_name}' for usecase {usecase_id}")
            return True
        except client.exceptions.ResourceNotFoundException:
            logger.info(f"Workflow definition '{workflow_name}' does not exist, nothing to delete")
            return True
        except Exception as e:
            logger.error(f"Error deleting workflow definition '{workflow_name}': {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error connecting to Nova Act service: {e}")
        return False

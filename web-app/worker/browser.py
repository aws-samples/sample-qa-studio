import boto3
import uuid
import os
import time
import logging
from datetime import datetime
from utils import get_region, validate_vpc_configuration, get_vpc_configuration
from bedrock_agentcore.tools.browser_client import BrowserClient

# Configure logging
logger = logging.getLogger(__name__)

def _create_client(region: str):
  control_client = boto3.client(
    'bedrock-agentcore-control',
    region_name=region,
    endpoint_url=f"https://bedrock-agentcore-control.{region}.amazonaws.com"
  )

  return control_client


def create_browser(unique_id: str, execution_id: str, artefact_bucket: str, artefact_prefix: str, region: str, browser_policy_s3_path: str = None):
  # Validate VPC configuration from environment variables
  is_valid, validation_message = validate_vpc_configuration()
  if not is_valid:
    logger.error(f"VPC configuration validation failed: {validation_message}")
    raise Exception(f"VPC configuration validation failed: {validation_message}")
  
  logger.info(f"Configuration validation: {validation_message}")
  
  # Determine network configuration based on AGENT_CORE_VPC environment variable
  agent_core_vpc = os.getenv('AGENT_CORE_VPC', 'false').lower() == 'true'
  
  cp_client = _create_client(region)
  
  if agent_core_vpc:
    # Get VPC Configuration from environment variables set by CDK worker-stack.ts
    vpc_config = get_vpc_configuration()
    
    if not vpc_config:
      raise Exception("AgentCoreVPC is enabled but VPC configuration could not be retrieved")
    
    vpc_id = vpc_config['vpc_id']
    subnet_id = vpc_config['subnet_id']
    security_group_id = vpc_config['security_group_id']
    
    logger.info(f"Creating browser with VPC settings from CDK stack:")
    logger.info(f"  VPC ID: {vpc_id}")
    logger.info(f"  Subnet ID: {subnet_id}")
    logger.info(f"  Security Group ID: {security_group_id}")
    
    # Browser configuration with VPC network settings
    browser_config = {
      'name': f"nova_act_qa_studio_{unique_id}",
      'description': f"VPC browser for {execution_id}",
      'networkConfiguration': {
          'networkMode': 'VPC',
          'vpcConfig': {
              'securityGroups': [security_group_id],
              'subnets': [subnet_id]
          }
      },
      'executionRoleArn': os.getenv('BEDROCK_EXECUTION_ROLE'),
      'clientToken': str(uuid.uuid4()),
      'recording': {
          'enabled': True,
          's3Location': {
              'bucket': artefact_bucket,
              'prefix': artefact_prefix
          }
      }
    }
  else:
    # Public network configuration
    logger.info("Creating browser with PUBLIC network settings")
    
    browser_config = {
      'name': f"nova_act_qa_studio_{unique_id}",
      'description': f"Public browser for {execution_id}",
      'networkConfiguration': {
          'networkMode': 'PUBLIC'
      },
      'executionRoleArn': os.getenv('BEDROCK_EXECUTION_ROLE'),
      'clientToken': str(uuid.uuid4()),
      'recording': {
          'enabled': True,
          's3Location': {
              'bucket': artefact_bucket,
              'prefix': artefact_prefix
          }
      }
    }
  
  logger.info("Browser configuration:")
  logger.info(f"  Name: {browser_config['name']}")
  logger.info(f"  Network Mode: {browser_config['networkConfiguration']['networkMode']}")

  # Add enterprise policies if a browser policy file is configured
  if browser_policy_s3_path:
    browser_config['enterprisePolicies'] = [
      {
        'type': 'MANAGED',
        'location': {
          's3': {
            'bucket': artefact_bucket,
            'prefix': browser_policy_s3_path
          }
        }
      }
    ]
    logger.info(f"  Enterprise Policy: s3://{artefact_bucket}/{browser_policy_s3_path}")
  if agent_core_vpc:
    logger.info(f"  VPC ID: {vpc_id}")
    logger.info(f"  Subnet IDs: {browser_config['networkConfiguration']['vpcConfig']['subnets']}")
    logger.info(f"  Security Group IDs: {browser_config['networkConfiguration']['vpcConfig']['securityGroups']}")
  logger.info(f"  Recording Bucket: {browser_config['recording']['s3Location']['bucket']}")
  logger.info(f"  Recording Prefix: {browser_config['recording']['s3Location']['prefix']}")
  
  try:
    # Start timing browser creation
    creation_start_time = time.time()
    logger.info(f"Starting browser creation at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    response = cp_client.create_browser(**browser_config)
    browser_id = response['browserId']
    logger.info(f"Browser creation request submitted with ID: {browser_id}")
    
    # Log additional response details if available
    if 'browserArn' in response:
        logger.info(f"Browser ARN: {response['browserArn']}")
    if 'status' in response:
        logger.info(f"Initial Browser Status: {response['status']}")
    
    # Wait for browser to be ready (both VPC and PUBLIC modes need this)
    network_type = "VPC" if agent_core_vpc else "PUBLIC"
    logger.info(f"Waiting for {network_type} browser to be ready...")
    browser_id = _wait_for_browser_ready(cp_client, browser_id, creation_start_time)
    
    return browser_id
    
  except Exception as e:
    network_type = "VPC" if agent_core_vpc else "PUBLIC"
    logger.error(f"Failed to create {network_type} browser: {e}")
    logger.error(f"Error type: {type(e).__name__}")
    
    # Try to provide more specific error information
    if hasattr(e, 'response'):
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        logger.error(f"AWS Error Code: {error_code}")
        logger.error(f"AWS Error Message: {error_message}")
    
    raise


def _wait_for_browser_ready(cp_client, browser_id: str, creation_start_time: float) -> str:
    """Wait for browser to be in READY state and track timing"""
    max_wait_time = 600  # 10 minutes maximum wait
    check_interval = 1  # Check every 1 second
    
    elapsed_time = 0
    check_count = 0
    
    while elapsed_time < max_wait_time:
        try:
            check_count += 1
            current_time = time.time()
            elapsed_time = current_time - creation_start_time
            
            # Get browser status
            response = cp_client.get_browser(browserId=browser_id)
            status = response.get('status', 'UNKNOWN')
            
            logger.info(f"Check #{check_count} - Browser status: {status} (elapsed: {elapsed_time:.1f}s)")
            
            if status == 'READY':
                total_creation_time = time.time() - creation_start_time
                logger.info(f"✅ Browser is READY! Total creation time: {total_creation_time:.1f} seconds ({total_creation_time/60:.1f} minutes)")
                return browser_id
            elif status in ['FAILED', 'DELETED']:
                logger.error(f"❌ Browser creation failed with status: {status}")
                raise Exception(f"Browser creation failed with status: {status}")
            elif status in ['CREATING', 'PENDING']:
                logger.info(f"⏳ Browser still creating... (status: {status})")
            else:
                logger.warning(f"⚠️ Unknown browser status: {status}")
            
            # Wait before next check
            time.sleep(check_interval)
            
        except Exception as e:
            if "does not exist" in str(e).lower():
                logger.error(f"❌ Browser {browser_id} not found. Creation may have failed.")
                raise Exception(f"Browser {browser_id} not found during status check")
            else:
                logger.warning(f"Error checking browser status: {e}")
                time.sleep(check_interval)
    
    # Timeout reached
    total_wait_time = time.time() - creation_start_time
    logger.error(f"❌ Timeout waiting for browser to be ready. Waited {total_wait_time:.1f} seconds ({total_wait_time/60:.1f} minutes)")
    raise Exception(f"Timeout waiting for browser to be ready after {total_wait_time:.1f} seconds")


def delete_browser(browser_id: str, region: str):
  cp_client = _create_client(region)
  cp_client.delete_browser(
    browserId=browser_id
  )


def start_browser(browser_id: str, execution_id: str, region: str, extensions: list = None):
  browser_client = BrowserClient(region)
  start_kwargs = {
    'identifier': browser_id,
    'name': execution_id,
  }
  if extensions:
    start_kwargs['extensions'] = extensions
  session_id = browser_client.start(**start_kwargs)

  return browser_client
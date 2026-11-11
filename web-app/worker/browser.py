import boto3
import time
import logging
from datetime import datetime
from bedrock_agentcore.tools.browser_client import BrowserClient
from qa_studio_cli.runner.browser.agentcore import build_browser_config

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
  """Create an AgentCore browser for a wizard session and wait until READY.

  The request body (network mode from ``AGENT_CORE_VPC`` / ``AC_*``, recording,
  enterprise policy) comes from the CLI's ``build_browser_config`` so batch and
  wizard browsers are configured by one implementation.  A VPC
  misconfiguration raises before any AWS client is created.
  """
  browser_config = build_browser_config(
    unique_id=unique_id,
    execution_id=execution_id,
    artefact_bucket=artefact_bucket,
    artefact_prefix=artefact_prefix,
    browser_policy_s3_path=browser_policy_s3_path,
  )
  network = browser_config['networkConfiguration']
  network_type = network['networkMode']
  vpc_config = network.get('vpcConfig') or {}

  logger.info("Browser configuration:")
  logger.info(f"  Name: {browser_config['name']}")
  logger.info(f"  Network Mode: {network_type}")
  if vpc_config:
    logger.info(f"  Subnet IDs: {vpc_config['subnets']}")
    logger.info(f"  Security Group IDs: {vpc_config['securityGroups']}")
  if browser_policy_s3_path:
    logger.info(f"  Enterprise Policy: s3://{artefact_bucket}/{browser_policy_s3_path}")
  logger.info(f"  Recording Bucket: {browser_config['recording']['s3Location']['bucket']}")
  logger.info(f"  Recording Prefix: {browser_config['recording']['s3Location']['prefix']}")

  cp_client = _create_client(region)

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
    logger.info(f"Waiting for {network_type} browser to be ready...")
    browser_id = _wait_for_browser_ready(cp_client, browser_id, creation_start_time)

    return browser_id

  except Exception as e:
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
            time.sleep(check_interval)  # nosemgrep
            
        except Exception as e:
            if "does not exist" in str(e).lower():
                logger.error(f"❌ Browser {browser_id} not found. Creation may have failed.")
                raise Exception(f"Browser {browser_id} not found during status check")
            else:
                logger.warning(f"Error checking browser status: {e}")
                # Intentional: poll before re-checking after an error (max_wait_time).
                time.sleep(check_interval)  # nosemgrep
    
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
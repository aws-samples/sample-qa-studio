import os
import json
from datetime import datetime
import boto3
import uuid

TIME_FORMAT='%Y-%m-%dT%H:%M:%SZ'
STRING_SCHEMA = {"type": "string"}
NUMBER_SCHEMA = {"type": "number"}
BOOL_SCHEMA = {"type": "boolean"}

def get_region(default='us-east-1'):
  """Get the AWS region from environment variables or use a default."""
  return os.getenv('AWS_REGION', default)

def remove_prefix(s, prefix):
    return s[len(prefix):] if s.startswith(prefix) else s

def get_time():
  return datetime.now().strftime(TIME_FORMAT)

def validate_vpc_configuration():
  """Validate VPC configuration parameters from environment variables"""
  # Check if AgentCore VPC mode is enabled via environment variable
  agent_core_vpc = os.getenv('AGENT_CORE_VPC', 'false').lower() == 'true'
  
  if not agent_core_vpc:
    return True, "VPC disabled - using PUBLIC network mode"
  
  # If AgentCoreVPC is true, validate that required environment variables are set
  # These should be set by the CDK worker-stack.ts
  required_env_vars = ['AC_VPC_ID', 'AC_SUBNET_ID', 'AC_SECURITY_GROUP_ID']
  missing_env_vars = []
  
  for env_var in required_env_vars:
    if not os.getenv(env_var):
      missing_env_vars.append(env_var)
  
  if missing_env_vars:
    error_msg = f"AgentCoreVPC is enabled but missing required environment variables: {', '.join(missing_env_vars)}. These should be set by the CDK worker-stack.ts"
    return False, error_msg
  
  return True, "VPC configuration validated successfully"

def get_vpc_configuration():
  """Get VPC configuration from environment variables set by CDK stack"""
  # Check if AgentCore VPC mode is enabled via environment variable
  agent_core_vpc = os.getenv('AGENT_CORE_VPC', 'false').lower() == 'true'
  
  if not agent_core_vpc:
    return None
  
  # Get VPC configuration from environment variables set by worker-stack.ts
  vpc_config = {
    'vpc_id': os.getenv('AC_VPC_ID'),
    'subnet_id': os.getenv('AC_SUBNET_ID'), 
    'security_group_id': os.getenv('AC_SECURITY_GROUP_ID')
  }
  
  return vpc_config


def _create_client():
  control_client = boto3.client(
    'bedrock-agentcore-control',
    region_name=get_region(),
    endpoint_url=f"https://bedrock-agentcore-control.{get_region()}.amazonaws.com"
  )

  return control_client

def create_browser(execution_id: str, artefact_bucket: str, artefact_prefix: str):
  cp_client = _create_client()
  response = cp_client.create_browser(
    name=execution_id,
    description=f"browser for {execution_id}",
    networkConfiguration={
        "networkMode": "PUBLIC"
    },
    executionRoleArn=os.getenv('BEDROCK_EXECUTION_ROLE'),
    clientToken=str(uuid.uuid4()),
    recording={
      "enabled": True,
      "s3Location": {
        "bucket": artefact_bucket,
        "prefix": artefact_prefix
      } 
    }
  )
    
  return response

def get_browser(browser_id: str):
  cp_client = _create_client()
  response = cp_client.get_browser(
    browserId=browser_id
  )

  return response


def delete_browser(browser_id: str):
  cp_client = _create_client()
  response = cp_client.delete_browser(
    browserId=browser_id
  )
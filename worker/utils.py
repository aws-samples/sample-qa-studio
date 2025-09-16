import os
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
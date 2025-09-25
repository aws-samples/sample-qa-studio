import boto3
import uuid
import os
from utils import get_region
from bedrock_agentcore.tools.browser_client import BrowserClient

def _create_client(region: str):
  control_client = boto3.client(
    'bedrock-agentcore-control',
    region_name=region,
    endpoint_url=f"https://bedrock-agentcore-control.{region}.amazonaws.com"
  )

  return control_client


def create_browser(unique_id: str,execution_id: str, artefact_bucket: str, artefact_prefix: str, region: str):
  cp_client = _create_client(region)
  response = cp_client.create_browser(
    name=f"nova_act_qa_studio_{unique_id}",
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
    
  return response['browserId']


def delete_browser(browser_id: str, region: str):
  cp_client = _create_client(region)
  cp_client.delete_browser(
    browserId=browser_id
  )


def start_browser(browser_id: str, execution_id: str, region: str):
  browser_client = BrowserClient(region)
  session_id = browser_client.start(
    identifier=browser_id,
    name=execution_id
    # session_timeout_seconds=100 #  The timeout for the session in seconds. Default to 3600.
  )

  return browser_client
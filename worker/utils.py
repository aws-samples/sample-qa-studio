import os
from datetime import datetime

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
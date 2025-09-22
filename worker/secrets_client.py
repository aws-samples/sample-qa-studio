#!/usr/bin/env python3
"""
Secrets Manager client for retrieving usecase secrets
"""

import boto3
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class SecretsMissingException(Exception):
  pass

class SecretsClient:
    def __init__(self, region_name: str = 'us-east-1'):
        """Initialize the Secrets Manager client"""
        self.client = boto3.client('secretsmanager', region_name=region_name)
        self.region_name = region_name
    
    def get_secret_value(self, usecase_id: str, secret_key: str) -> Optional[str]:
        """
        Get the value of a specific secret for a usecase
        
        Args:
            usecase_id: The usecase ID
            secret_key: The secret key name
            
        Returns:
            The secret value as a string, or None if retrieval fails
        """
        secret_name = f"{os.getenv('SECRETS_PREFIX')}/usecase/{usecase_id}/{secret_key}"
        print(secret_name)
        
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            secret_value = response.get('SecretString')
            logger.info(f"Successfully retrieved secret: {secret_key}")
            return secret_value
            
        except Exception as e:
            logger.error(f"Error retrieving secret value for {secret_name}: {e}")
            return None
    
    
    
    def _get_secret_value_by_name(self, secret_name: str) -> Optional[str]:
        """
        Get the value of a secret by its full name
        
        Args:
            secret_name: The full name/ARN of the secret
            
        Returns:
            The secret value as a string, or None if retrieval fails
        """
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            return response.get('SecretString')
            
        except Exception as e:
            logger.error(f"Error retrieving secret value for {secret_name}: {e}")
            return None
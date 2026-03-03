import boto3
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SQSClient:
    def __init__(self, region_name: str = 'us-east-1'):
        self.sqs = boto3.client('sqs', region_name=region_name)
    
    def send_notification_message(self, queue_url: str, usecase_id: str, execution_id: str) -> bool:
        """Send notification message to SQS queue"""
        try:
            message = {
                "usecase_id": usecase_id,
                "execution_id": execution_id
            }
            
            response = self.sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'usecase_id': {
                        'StringValue': usecase_id,
                        'DataType': 'String'
                    },
                    'execution_id': {
                        'StringValue': execution_id,
                        'DataType': 'String'
                    }
                }
            )
            
            logger.info(f"Sent notification message for execution {execution_id} of usecase {usecase_id}")
            logger.debug(f"SQS Message ID: {response['MessageId']}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending notification message for execution {execution_id}: {e}")
            return False
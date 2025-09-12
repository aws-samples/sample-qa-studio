#!/usr/bin/env python3
"""
Entry point script for the Nova Act worker.
Polls SQS queue for execution messages and processes them.
"""

import sys
import os
import json
import logging
import time
import boto3
from botocore.exceptions import ClientError

# Add the worker directory to Python path so we can import the modules
worker_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'worker')
sys.path.insert(0, worker_dir)

from worker import main as process_execution

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SQSWorker:
    def __init__(self, queue_url: str, region_name: str = 'us-east-1'):
        self.queue_url = queue_url
        self.sqs = boto3.client('sqs', region_name=region_name)
        self.running = True
    
    def poll_queue(self):
        """Poll SQS queue for messages and process them"""
        logger.info(f"Starting SQS worker, polling queue: {self.queue_url}")
        
        while self.running:
            try:
                # Receive messages from SQS
                response = self.sqs.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,  # Long polling
                    MessageAttributeNames=['All']
                )
                
                messages = response.get('Messages', [])
                
                if not messages:
                    logger.debug("No messages received, continuing to poll...")
                    continue
                
                for message in messages:
                    try:
                        # Process the message
                        success = self.process_message(message)
                        
                        if success:
                            # Delete message from queue on successful processing
                            self.delete_message(message)
                            logger.info(f"Message processed successfully and deleted from queue")
                        else:
                            logger.error(f"Message processing failed, leaving in queue")
                    
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        # Don't delete message on error, let it be retried
            
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down...")
                self.running = False
                break
            
            except Exception as e:
                logger.error(f"Error polling SQS queue: {e}")
                time.sleep(5)  # Wait before retrying
    
    def process_message(self, message) -> bool:
        """Process a single SQS message"""
        try:
            # Parse message body
            body = json.loads(message['Body'])
            
            # Extract execution details from message
            execution_id = body.get('execution_id')
            usecase_id = body.get('usecase_id')
            
            if not execution_id or not usecase_id:
                logger.error(f"Invalid message format: missing execution_id or usecase_id")
                return False
            
            logger.info(f"Processing execution: {execution_id} for usecase: {usecase_id}")
            
            # Set environment variables for the worker
            os.environ['EXECUTION_ID'] = execution_id
            os.environ['USECASE_ID'] = usecase_id
            
            # Process the execution
            success = process_execution()
            
            if success:
                logger.info(f"Successfully processed execution {execution_id}")
            else:
                logger.error(f"Failed to process execution {execution_id}")
            
            return success
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message body as JSON: {e}")
            return False
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return False
    
    def delete_message(self, message):
        """Delete message from SQS queue"""
        try:
            self.sqs.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=message['ReceiptHandle']
            )
        except ClientError as e:
            logger.error(f"Failed to delete message from queue: {e}")


def main():
    """Main entry point"""
    
    # Get configuration from environment variables
    queue_url = os.getenv('SQS_QUEUE_URL')
    region_name = os.getenv('AWS_REGION', 'us-east-1')
    
    # Check if we should run in SQS mode or single execution mode
    if queue_url:
        # SQS mode - poll queue for messages
        logger.info("Running in SQS mode")
        worker = SQSWorker(queue_url, region_name)
        worker.poll_queue()
    else:
        # Single execution mode - process one execution from env vars
        logger.info("Running in single execution mode")
        usecase_id = os.getenv('USECASE_ID')
        execution_id = os.getenv('EXECUTION_ID')
        
        if not usecase_id or not execution_id:
            logger.error("USECASE_ID and EXECUTION_ID environment variables are required for single execution mode")
            return False
        
        success = process_execution()
        return True


if __name__ == "__main__":
    try:
        result = main()
        if isinstance(result, bool):
            sys.exit(0 if result else 1)
        else:
            sys.exit(0)  # SQS mode doesn't return a boolean
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        sys.exit(0)
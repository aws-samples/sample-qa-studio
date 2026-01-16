import boto3
from typing import Optional, List
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
import logging
import os
import json

from models import Execution, ExecutionStep, ExecutionVariables, KeyValuePair, ExecutionHeaders
from sqs_client import SQSClient
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DynamoDBClient:
    def __init__(self, table_name: str, region_name: str = 'us-east-1'):
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
        self.sqs_client = SQSClient(region_name)
        self.notification_queue_url = os.getenv('NOTIFICATION_QUEUE_URL')
        self.eventbridge_client = boto3.client('events', region_name=region_name)
        self.event_bus_name = os.getenv('EVENT_BUS_NAME', 'default')
    
    def get_execution(self, usecase_id: str, execution_id: str) -> Optional[Execution]:
        """Load execution data from DynamoDB"""
        try:
            response = self.table.get_item(
                Key={
                    'pk': f'USECASE_EXECUTION#{usecase_id}',
                    'sk': f'EXECUTION#{execution_id}'
                }
            )
            
            if 'Item' not in response:
                logger.warning(f"Execution {execution_id} not found for usecase {usecase_id}")
                return None
            
            item = response['Item']
            return Execution(
                pk=item['pk'],
                sk=item['sk'],
                status=item['status'],
                starting_url=item['starting_url'],
                created_at=item['created_at'],
                completed_at=item.get('completed_at'),
                executing_at=item.get('executing_at'),
                trigger_type=item.get('trigger_type'),
                session_id=item.get('session_id'),
                region=item.get('execution_region', 'us-east-1')
            )
            
        except ClientError as e:
            logger.error(f"Error getting execution {execution_id} for usecase {usecase_id}: {e}")
            return None
    
    def get_execution_steps(self, usecase_id: str, execution_id: str) -> List[ExecutionStep]:
        """Load execution steps from DynamoDB"""
        try:
            response = self.table.query(
                KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & 
                                     Key('sk').begins_with(f'EXECUTION_STEP#'),
                ScanIndexForward=True
            )
            
            steps = []
            for item in response['Items']:
                # Defensive field access with defaults
                try:
                    step = ExecutionStep(
                        pk=item.get('pk', ''),
                        sk=item.get('sk', ''),
                        step_id=item.get('step_id', ''),
                        sort=item.get('sort', 0),
                        instruction=item.get('instruction', ''),
                        artefact=item.get('artefact', ''),
                        logs=item.get('logs', []),
                        created_at=item.get('created_at', ''),
                        secret_key=item.get('secret_key', ''),
                        step_type=item.get('step_type', ''),
                        validation_type=item.get('validation_type', ''),
                        validation_operator=item.get('validation_operator', ''),
                        validation_value=item.get('validation_value', ''),
                        capture_variable=item.get('capture_variable', ''),
                        value_type=item.get('value_type', ''),
                        assertion_variable=item.get('assertion_variable', '')
                    )
                    steps.append(step)
                except Exception as e:
                    logger.error(f"Error parsing step {item.get('sk', 'unknown')}: {e}")
                    logger.error(f"Step data: {item}")
                    continue
            
            # Sort by sort field to ensure proper order
            steps.sort(key=lambda x: x.sort)
            return steps
            
        except ClientError as e:
            logger.error(f"Error getting execution steps for {execution_id} in usecase {usecase_id}: {e}")
            return []
    
    def get_execution_variables(self, execution_id: str) -> Optional[ExecutionVariables]:
        """Load execution variables from DynamoDB"""
        try:
            response = self.table.get_item(
                Key={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': f'EXECUTION_VARIABLES'
                }
            )
            
            if 'Item' not in response:
                logger.info(f"No variables found for execution {execution_id}")
                return None
            
            item = response['Item']

            # Handle both uppercase and lowercase keys for compatibility
            variables = []
            for var in item.get('variables', []):
                if isinstance(var, dict):
                    key = var.get('key') or var.get('Key', '')
                    value = var.get('value') or var.get('Value', '')
                    variables.append(KeyValuePair(key=key, value=value))
            
            runtime_variables = []
            for var in item.get('runtime_variables', []):
                if isinstance(var, dict):
                    key = var.get('key') or var.get('Key', '')
                    value = var.get('value') or var.get('Value', '')
                    runtime_variables.append(KeyValuePair(key=key, value=value))
            
            return ExecutionVariables(
                pk=item.get('pk', ''),
                sk=item.get('sk', ''),
                variables=variables,
                runtime_variables=runtime_variables,
                created_at=item.get('created_at', '')
            )
            
        except ClientError as e:
            logger.error(f"Error getting execution variables for {execution_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting execution variables for {execution_id}: {e}")
            logger.error(f"Item data: {item if 'item' in locals() else 'N/A'}")
            return None
    
    def update_execution_status(self, usecase_id: str, execution_id: str, status: str, 
                              executing_at: Optional[str] = None, completed_at: Optional[str] = None) -> bool:
        """Update execution status in DynamoDB"""
        try:
            update_expression = "SET #status = :status"
            expression_attribute_names = {"#status": "status"}
            expression_attribute_values = {":status": status}
            
            if executing_at:
                update_expression += ", executing_at = :executing_at"
                expression_attribute_values[":executing_at"] = executing_at
            
            if completed_at:
                update_expression += ", completed_at = :completed_at"
                expression_attribute_values[":completed_at"] = completed_at
            
            self.table.update_item(
                Key={
                    'pk': f'USECASE_EXECUTION#{usecase_id}',
                    'sk': f'EXECUTION#{execution_id}'
                },
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values
            )
            
            logger.info(f"Updated execution {execution_id} status to {status} for usecase {usecase_id}")
            
            # Publish EventBridge event for execution status change
            self._publish_execution_status_event(usecase_id, execution_id, status, completed_at)
            
            # Send notification if execution failed and notification queue is configured
            if status in ['failed', 'error'] and self.notification_queue_url:
                self.sqs_client.send_notification_message(
                    self.notification_queue_url, 
                    usecase_id, 
                    execution_id
                )
            
            return True
            
        except ClientError as e:
            logger.error(f"Error updating execution {execution_id} status for usecase {usecase_id}: {e}")
            return False
    
    def _publish_execution_status_event(self, usecase_id: str, execution_id: str, status: str, 
                                       completed_at: Optional[str] = None) -> None:
        """Publish execution status change event to EventBridge"""
        try:
            event_detail = {
                'usecase_id': usecase_id,
                'execution_id': execution_id,
                'status': status,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            if completed_at:
                event_detail['completed_at'] = completed_at
            
            self.eventbridge_client.put_events(
                Entries=[
                    {
                        'Source': 'nova-act-qa-studio.execution',
                        'DetailType': 'nova-act-qa-studio.execution.status.changed',
                        'Detail': json.dumps(event_detail),
                        'EventBusName': self.event_bus_name
                    }
                ]
            )
            
            logger.info(f"Published execution status event: {usecase_id}/{execution_id} -> {status}")
            
        except Exception as e:
            # Log error but don't fail the execution update
            logger.error(f"Failed to publish execution status event: {e}")
            logger.error(f"Event details: usecase_id={usecase_id}, execution_id={execution_id}, status={status}")
    
    def update_execution_session_id(self, usecase_id: str, execution_id: str, session_id: str) -> bool:
        """Update execution with Nova Act session ID in DynamoDB"""
        try:
            self.table.update_item(
                Key={
                    'pk': f'USECASE_EXECUTION#{usecase_id}',
                    'sk': f'EXECUTION#{execution_id}'
                },
                UpdateExpression="SET nova_session_id = :session_id",
                ExpressionAttributeValues={":session_id": session_id}
            )
            
            logger.info(f"Updated execution {execution_id} with session_id {session_id} for usecase {usecase_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Error updating execution {execution_id} session_id for usecase {usecase_id}: {e}")
            return False
    
    def update_execution_step_status(self, execution_id: str, step_id: str, 
                                   act_id: str, status: str, logs: str = '', actual_value: str = '') -> bool:
        """Update execution step with ActID and status in DynamoDB"""
        try:
            # Update the step with act_id and status
            self.table.update_item(
                Key={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': f'EXECUTION_STEP#{step_id}',
                },
                UpdateExpression="SET act_id = :act_id, #status = :status, #logs = :logs, #actual_value = :actual_value",
                ExpressionAttributeNames={
                    "#status": "status",
                    "#logs": "logs",
                    "#actual_value": "actual_value",
                },
                ExpressionAttributeValues={
                    ":act_id": act_id,
                    ":status": status,
                    ":logs": logs,
                    ":actual_value": actual_value,
                }
            )
            
            logger.info(f"Updated step {step_id} with act_id {act_id} and status {status}")
            return True
            
        except ClientError as e:
            logger.error(f"Error updating step {step_id} status: {e}")
            return False
    
    def update_runtime_variables(self, execution_id: str, runtime_variables: List[KeyValuePair]) -> bool:
        """Update runtime variables for an execution in DynamoDB"""
        logger.info(f"Updating runtime variables for execution {execution_id}")
        try:
            # Convert runtime variables to DynamoDB format
            runtime_vars_db = [
                {"Key": var.key, "Value": var.value}
                for var in runtime_variables
            ]
            
            # First check if the EXECUTION_VARIABLES record exists
            try:
                response = self.table.get_item(
                    Key={
                        'pk': f'EXECUTION#{execution_id}',
                        'sk': f'EXECUTION_VARIABLES'
                    }
                )
                
                if 'Item' in response:
                    # Record exists, update it
                    self.table.update_item(
                        Key={
                            'pk': f'EXECUTION#{execution_id}',
                            'sk': f'EXECUTION_VARIABLES'
                        },
                        UpdateExpression="SET runtime_variables = :runtime_variables",
                        ExpressionAttributeValues={
                            ":runtime_variables": runtime_vars_db
                        }
                    )
                else:
                    # Record doesn't exist, create it
                    from utils import get_time
                    self.table.put_item(
                        Item={
                            'pk': f'EXECUTION#{execution_id}',
                            'sk': f'EXECUTION_VARIABLES',
                            'variables': [],  # Empty regular variables
                            'runtime_variables': runtime_vars_db,
                            'created_at': get_time()
                        }
                    )
                
                logger.info(f"Updated runtime variables for execution {execution_id}")
                return True
                
            except ClientError as e:
                logger.error(f"Error updating runtime variables for execution {execution_id}: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Unexpected error updating runtime variables for execution {execution_id}: {e}")
            return False
    
    def get_execution_headers(self, execution_id: str) -> Optional[ExecutionHeaders]:
        """Load execution headers from DynamoDB"""
        try:
            response = self.table.get_item(
                Key={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': f'HEADERS'
                }
            )
            
            if 'Item' not in response:
                logger.info(f"No headers found for execution {execution_id}")
                return None
            
            item = response['Item']
            
            return ExecutionHeaders(
                pk=item.get('pk', ''),
                sk=item.get('sk', ''),
                headers=item.get('headers', {}),
                created_at=item.get('created_at', '')
            )
            
        except ClientError as e:
            logger.error(f"Error getting execution headers for {execution_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting execution headers for {execution_id}: {e}")
            return None

    def create_live_view(self, execution_id: str, live_url: str) -> bool:
        """Create a live view record for an execution in DynamoDB"""
        try:
            from utils import get_time
            
            # Calculate expiration time (24 hours from now)
            expires_at = int((datetime.now() + timedelta(hours=24)).timestamp())
            
            self.table.put_item(
                Item={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': 'LIVE_VIEW',
                    'live_url': live_url,
                    'created_at': get_time(),
                    'expires_at': expires_at
                }
            )
            
            logger.info(f"Created live view record for execution {execution_id} with URL: {live_url}")
            return True
            
        except ClientError as e:
            logger.error(f"Error creating live view for execution {execution_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating live view for execution {execution_id}: {e}")
            return False
    
    def delete_live_view(self, execution_id: str) -> bool:
        """Delete the live view record for an execution from DynamoDB"""
        try:
            self.table.delete_item(
                Key={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': 'LIVE_VIEW'
                }
            )
            
            logger.info(f"Deleted live view record for execution {execution_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting live view for execution {execution_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting live view for execution {execution_id}: {e}")
            return False
    
    def update_live_view(self, execution_id: str, live_url: str) -> bool:
        """Update the live view URL for an execution in DynamoDB"""
        try:
            from utils import get_time
            
            # Calculate new expiration time (24 hours from now)
            expires_at = int((datetime.now() + timedelta(hours=24)).timestamp())
            
            self.table.update_item(
                Key={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': 'LIVE_VIEW'
                },
                UpdateExpression="SET live_url = :live_url, updated_at = :updated_at, expires_at = :expires_at",
                ExpressionAttributeValues={
                    ":live_url": live_url,
                    ":updated_at": get_time(),
                    ":expires_at": expires_at
                }
            )
            
            logger.info(f"Updated live view URL for execution {execution_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Error updating live view for execution {execution_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating live view for execution {execution_id}: {e}")
            return False

    def update_execution_last_activity(self, usecase_id: str, execution_id: str, timestamp: str) -> bool:
        """Update last activity timestamp for wizard execution"""
        try:
            self.table.update_item(
                Key={
                    'pk': f'USECASE_EXECUTION#{usecase_id}',
                    'sk': f'EXECUTION#{execution_id}'
                },
                UpdateExpression="SET last_activity = :timestamp",
                ExpressionAttributeValues={
                    ":timestamp": timestamp
                }
            )
            return True
        except ClientError as e:
            logger.error(f"Error updating last activity for execution {execution_id}: {e}")
            return False

    def get_execution_step(self, execution_id: str, step_id: str) -> Optional[ExecutionStep]:
        """Get a single execution step by ID"""
        try:
            response = self.table.get_item(
                Key={
                    'pk': f'EXECUTION#{execution_id}',
                    'sk': f'EXECUTION_STEP#{step_id}'
                }
            )
            
            if 'Item' not in response:
                return None
            
            item = response['Item']
            return ExecutionStep(
                pk=item['pk'],
                sk=item['sk'],
                step_id=item['step_id'],
                sort=item.get('sort', 0),
                instruction=item['instruction'],
                artefact=item.get('artefact', ''),
                logs=item.get('logs', []),
                created_at=item['created_at'],
                secret_key=item.get('secret_key', ''),
                step_type=item['step_type'],
                validation_type=item.get('validation_type', ''),
                validation_operator=item.get('validation_operator', ''),
                validation_value=item.get('validation_value', ''),
                capture_variable=item.get('capture_variable', ''),
                value_type=item.get('value_type', ''),
                assertion_variable=item.get('assertion_variable', '')
            )
        except ClientError as e:
            logger.error(f"Error getting execution step {step_id}: {e}")
            return None

    def get_accepted_execution_steps(self, execution_id: str) -> List[ExecutionStep]:
        """Get all accepted steps for wizard execution, sorted by sort order"""
        try:
            response = self.table.query(
                KeyConditionExpression=Key('pk').eq(f'EXECUTION#{execution_id}') & 
                                     Key('sk').begins_with(f'EXECUTION_STEP#'),
                FilterExpression='acceptance_status = :status',
                ExpressionAttributeValues={
                    ':status': 'accepted'
                },
                ScanIndexForward=True
            )
            
            steps = []
            for item in response['Items']:
                step = ExecutionStep(
                    pk=item['pk'],
                    sk=item['sk'],
                    step_id=item['step_id'],
                    sort=item['sort'],
                    instruction=item['instruction'],
                    artefact=item.get('artefact', ''),
                    logs=item.get('logs', []),
                    created_at=item['created_at'],
                    secret_key=item.get('secret_key', ''),
                    step_type=item['step_type'],
                    validation_type=item.get('validation_type', ''),
                    validation_operator=item.get('validation_operator', ''),
                    validation_value=item.get('validation_value', ''),
                    capture_variable=item.get('capture_variable', ''),
                    value_type=item.get('value_type', ''),
                    assertion_variable=item.get('assertion_variable', '')
                )
                steps.append(step)
            
            # Sort by sort field
            steps.sort(key=lambda x: x.sort)
            return steps
            
        except ClientError as e:
            logger.error(f"Error getting accepted execution steps for {execution_id}: {e}")
            return []

    def poll_wizard_commands(self, session_id: str, limit: int = 1) -> List[dict]:
        """
        Poll DynamoDB for wizard commands for a specific session.
        Returns commands in chronological order (oldest first).
        """
        try:
            response = self.table.query(
                KeyConditionExpression=Key('pk').eq(f'WIZARD_COMMAND#{session_id}'),
                ScanIndexForward=True,  # Oldest first
                Limit=limit
            )
            
            commands = response.get('Items', [])
            logger.info(f"Polled {len(commands)} command(s) for session {session_id}")
            return commands
            
        except ClientError as e:
            logger.error(f"Error polling wizard commands for session {session_id}: {e}")
            return []
    
    def delete_wizard_command(self, session_id: str, command_sk: str) -> bool:
        """Delete a wizard command after processing"""
        try:
            self.table.delete_item(
                Key={
                    'pk': f'WIZARD_COMMAND#{session_id}',
                    'sk': command_sk
                }
            )
            logger.info(f"Deleted command {command_sk} for session {session_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting wizard command: {e}")
            return False

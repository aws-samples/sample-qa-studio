import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from execute_usecase import handler


class TestExecuteUsecaseCiRunner(unittest.TestCase):
    """Test suite for execute_usecase Lambda with ci_runner trigger type"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['DEFAULT_REGION'] = 'us-east-1'
        os.environ['S3_BUCKET_PREFIX'] = 'test-bucket'
        os.environ['AWS_REGION'] = 'us-east-1'
        
    def test_ci_runner_creates_execution_record(self):
        """Test that ci_runner trigger creates execution record without ECS task"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb, \
             patch('execute_usecase.eventbridge') as mock_eventbridge:
            
            # Mock usecase lookup
            mock_dynamodb.get_item.return_value = {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'test-model'}
                }
            }
            
            # Mock steps query
            mock_dynamodb.query.return_value = {
                'Items': [
                    {
                        'id': {'S': 'step-1'},
                        'sort': {'N': '1'},
                        'instruction': {'S': 'Test instruction'},
                        'step_type': {'S': 'action'}
                    }
                ]
            }
            
            response = handler(event, None)
            
            # Verify response
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'execution created')
            self.assertEqual(body['usecaseId'], 'test-usecase-123')
            self.assertIn('executionId', body)
            
            # Verify execution record was created
            put_item_calls = [call for call in mock_dynamodb.put_item.call_args_list]
            execution_call = put_item_calls[0]
            execution_item = execution_call[1]['Item']
            self.assertEqual(execution_item['trigger_type']['S'], 'ci_runner')
            self.assertEqual(execution_item['status']['S'], 'pending')
            
            # Verify no ECS task was started (ecs client not called)
            # This is implicit - if ECS was called, the test would fail
    
    def test_ci_runner_copies_steps(self):
        """Test that ci_runner execution copies steps correctly"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb, \
             patch('execute_usecase.eventbridge'):
            
            mock_dynamodb.get_item.return_value = {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'test-model'}
                }
            }
            
            # Mock multiple steps
            mock_dynamodb.query.return_value = {
                'Items': [
                    {
                        'id': {'S': 'step-1'},
                        'sort': {'N': '1'},
                        'instruction': {'S': 'Step 1'},
                        'step_type': {'S': 'action'}
                    },
                    {
                        'id': {'S': 'step-2'},
                        'sort': {'N': '2'},
                        'instruction': {'S': 'Step 2'},
                        'step_type': {'S': 'validation'}
                    }
                ]
            }
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            # Verify steps were copied (1 execution + 2 steps + hooks/vars/headers attempts)
            put_item_calls = mock_dynamodb.put_item.call_args_list
            # First call is execution, next 2 are steps
            step_calls = [call for call in put_item_calls if 'EXECUTION_STEP#' in call[1]['Item']['sk']['S']]
            self.assertEqual(len(step_calls), 2)
    
    def test_ci_runner_copies_hooks_variables_headers(self):
        """Test that ci_runner execution copies hooks, variables, and headers"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb, \
             patch('execute_usecase.eventbridge'):
            
            # Mock usecase and steps
            def get_item_side_effect(*args, **kwargs):
                key = kwargs['Key']
                if key['sk']['S'].startswith('USECASE#'):
                    return {
                        'Item': {
                            'starting_url': {'S': 'https://example.com'},
                            'executing_region': {'S': 'us-east-1'},
                            'model_id': {'S': 'test-model'}
                        }
                    }
                elif key['sk']['S'] == 'HOOKS':
                    return {
                        'Item': {
                            'before_script': {'S': 'console.log("before")'},
                            'after_script': {'S': 'console.log("after")'}
                        }
                    }
                elif key['sk']['S'] == 'USECASE_VARIABLES':
                    return {
                        'Item': {
                            'variables': {'M': {'var1': {'S': 'value1'}}}
                        }
                    }
                elif key['sk']['S'] == 'HEADERS':
                    return {
                        'Item': {
                            'headers': {'M': {'Authorization': {'S': 'Bearer token'}}}
                        }
                    }
                return {}
            
            mock_dynamodb.get_item.side_effect = get_item_side_effect
            mock_dynamodb.query.return_value = {'Items': []}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            # Verify hooks, variables, and headers were copied
            put_item_calls = mock_dynamodb.put_item.call_args_list
            hooks_call = [call for call in put_item_calls if call[1]['Item']['sk']['S'] == 'HOOKS']
            vars_call = [call for call in put_item_calls if call[1]['Item']['sk']['S'] == 'EXECUTION_VARIABLES']
            headers_call = [call for call in put_item_calls if call[1]['Item']['sk']['S'] == 'HEADERS']
            
            self.assertEqual(len(hooks_call), 1)
            self.assertEqual(len(vars_call), 1)
            self.assertEqual(len(headers_call), 1)


class TestExecuteUsecaseBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility for existing trigger types"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['DEFAULT_REGION'] = 'us-east-1'
        os.environ['S3_BUCKET_PREFIX'] = 'test-bucket'
        os.environ['AWS_REGION'] = 'us-east-1'
        os.environ['QUEUE_URL'] = 'https://sqs.us-east-1.amazonaws.com/123456789/test-queue'
        os.environ['ECS_CLUSTER'] = 'test-cluster'
        os.environ['ECS_TASK_DEFINITION'] = 'test-task-def'
        os.environ['SUBNET_ID'] = 'subnet-123'
        os.environ['SECURITY_GROUP_ID'] = 'sg-123'
        os.environ['BEDROCK_EXECUTION_ROLE'] = 'arn:aws:iam::123456789:role/test-role'
        os.environ['NOVA_ACT_API_KEY_NAME'] = 'test-api-key'
        os.environ['SECRETS_PREFIX'] = 'test-prefix'
        
    def test_ondemand_trigger_sends_to_sqs(self):
        """Test that OnDemand trigger sends message to SQS queue"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'queryStringParameters': {'trigger-type': 'OnDemand'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb, \
             patch('execute_usecase.sqs') as mock_sqs, \
             patch('execute_usecase.eventbridge'):
            
            mock_dynamodb.get_item.return_value = {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'test-model'}
                }
            }
            mock_dynamodb.query.return_value = {'Items': []}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'usecase queued')
            
            # Verify SQS was called
            mock_sqs.send_message.assert_called_once()
            call_args = mock_sqs.send_message.call_args[1]
            self.assertEqual(call_args['QueueUrl'], os.environ['QUEUE_URL'])
    
    def test_scheduled_trigger_spawns_ecs_task(self):
        """Test that Scheduled trigger spawns ECS task"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'queryStringParameters': {'trigger-type': 'Scheduled'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb, \
             patch('execute_usecase.ecs') as mock_ecs, \
             patch('execute_usecase.eventbridge'):
            
            mock_dynamodb.get_item.return_value = {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'test-model'}
                }
            }
            mock_dynamodb.query.return_value = {'Items': []}
            
            mock_ecs.run_task.return_value = {
                'tasks': [{
                    'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/cluster/task-123'
                }]
            }
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'task started')
            self.assertIn('taskArn', body)
            
            # Verify ECS was called
            mock_ecs.run_task.assert_called_once()
    
    def test_ondemandheadless_trigger_spawns_ecs_task(self):
        """Test that OnDemandHeadless trigger spawns ECS task"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'queryStringParameters': {'trigger-type': 'OnDemandHeadless'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb, \
             patch('execute_usecase.ecs') as mock_ecs, \
             patch('execute_usecase.eventbridge'):
            
            mock_dynamodb.get_item.return_value = {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'test-model'}
                }
            }
            mock_dynamodb.query.return_value = {'Items': []}
            
            mock_ecs.run_task.return_value = {
                'tasks': [{
                    'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/cluster/task-123'
                }]
            }
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'task started')
    
    def test_default_trigger_type_is_ondemand(self):
        """Test that default trigger type is OnDemand when not specified"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb, \
             patch('execute_usecase.sqs') as mock_sqs, \
             patch('execute_usecase.eventbridge'):
            
            mock_dynamodb.get_item.return_value = {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'test-model'}
                }
            }
            mock_dynamodb.query.return_value = {'Items': []}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'usecase queued')
            
            # Verify SQS was called (OnDemand behavior)
            mock_sqs.send_message.assert_called_once()


class TestExecuteUsecaseValidation(unittest.TestCase):
    """Test validation logic for execute_usecase"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        
    def test_invalid_trigger_type_returns_400(self):
        """Test that invalid trigger type returns 400 error"""
        event = {
            'pathParameters': {'id': 'test-usecase-123'},
            'queryStringParameters': {'trigger-type': 'InvalidType'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid trigger type', body['error'])
        self.assertIn('InvalidType', body['error'])
    
    def test_missing_usecase_id_returns_400(self):
        """Test that missing usecase ID returns 400 error"""
        event = {
            'pathParameters': {},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing usecase ID', body['error'])
    
    def test_usecase_not_found_returns_404(self):
        """Test that non-existent usecase returns 404 error"""
        event = {
            'pathParameters': {'id': 'non-existent-usecase'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/execution.write'
                }
            }
        }
        
        with patch('execute_usecase.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.return_value = {}  # No Item
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 404)
            body = json.loads(response['body'])
            self.assertIn('Usecase not found', body['error'])


if __name__ == '__main__':
    unittest.main()

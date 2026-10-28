import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from execute_usecase import handler

# Authorized caller for the behavior tests: executor in the owning team.
EXECUTOR_TEAM_A = json.dumps([{'team_id': 'team-a', 'role': 'executor'}])
_OWNED_USECASE = {'application_id': 'app-1', 'owner_team_id': 'team-a', 'created_by': None}


def setUpModule():
    global _owner_patch
    _owner_patch = patch('resource_auth.get_usecase_owner', return_value=_OWNED_USECASE)
    _owner_patch.start()


def tearDownModule():
    _owner_patch.stop()


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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('usecase ID is required', body['error'])
    
    def test_usecase_not_found_returns_404(self):
        """Test that non-existent usecase returns 404 error"""
        event = {
            'pathParameters': {'id': 'non-existent-usecase'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/usecases.execute',
                    'teamRoles': EXECUTOR_TEAM_A
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


# ---------------------------------------------------------------------------
# H-2 / N-1: scope + execute check, worker capability token
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402

_ECS_ENV = {
    'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1', 'S3_BUCKET_PREFIX': 'b',
    'AWS_REGION': 'us-east-1', 'ECS_CLUSTER': 'c', 'ECS_TASK_DEFINITION': 't', 'SUBNET_ID': 's',
    'SECURITY_GROUP_ID': 'g', 'BEDROCK_EXECUTION_ROLE': 'r', 'NOVA_ACT_API_KEY_NAME': 'k',
    'SECRETS_PREFIX': 'p', 'QUEUE_URL': 'q',
}


def _exec_event(trigger='OnDemandHeadless', scope='api/usecases.execute', team_roles=EXECUTOR_TEAM_A,
                identity_type='user'):
    authorizer = {'sub': 'u', 'email': 'u@example.com', 'identityType': identity_type,
                  'scope': scope, 'teamRoles': team_roles}
    if identity_type != 'user':
        authorizer.update({'email': '', 'clientId': 'client-1'})
    return {
        'pathParameters': {'id': 'uc-1'},
        'queryStringParameters': {'trigger-type': trigger},
        'requestContext': {'authorizer': authorizer},
    }


def _usecase_item():
    return {'Item': {'starting_url': {'S': 'https://example.com'}, 'executing_region': {'S': 'us-east-1'},
                     'model_id': {'S': 'm'}, 'application_id': {'S': 'app-1'}}}


@patch.dict(os.environ, _ECS_ENV)
@patch('execute_usecase.eventbridge')
@patch('execute_usecase.ecs')
@patch('execute_usecase.dynamodb')
class TestExecuteUsecaseAuthz(unittest.TestCase):
    def _run_ecs(self, mock_dynamodb, mock_ecs, event):
        mock_dynamodb.get_item.side_effect = lambda **kw: (
            _usecase_item() if kw['Key']['sk']['S'].startswith('USECASE#') else {})
        mock_dynamodb.query.return_value = {'Items': []}
        mock_ecs.run_task.return_value = {'tasks': [{'taskArn': 'arn:aws:ecs:r:a:task/c/task-1'}], 'failures': []}
        return handler(event, None)

    def test_token_hash_stored_and_token_injected(self, mock_dynamodb, mock_ecs, _):
        resp = self._run_ecs(mock_dynamodb, mock_ecs, _exec_event())
        self.assertEqual(resp['statusCode'], 200)
        item = mock_dynamodb.put_item.call_args_list[0].kwargs['Item']
        stored_hash = item['worker_token_hash']['S']
        env = {e['name']: e['value'] for e in
               mock_ecs.run_task.call_args.kwargs['overrides']['containerOverrides'][0]['environment']}
        token = env['EXECUTION_TOKEN']
        self.assertGreaterEqual(len(token), 40)
        self.assertEqual(hashlib.sha256(token.encode()).hexdigest(), stored_hash)
        self.assertNotIn(token, json.dumps(item))
        self.assertNotIn(token, resp['body'])

    def test_each_execution_gets_its_own_token(self, mock_dynamodb, mock_ecs, _):
        self._run_ecs(mock_dynamodb, mock_ecs, _exec_event())
        first = mock_dynamodb.put_item.call_args_list[0].kwargs['Item']['worker_token_hash']['S']
        mock_dynamodb.reset_mock()
        self._run_ecs(mock_dynamodb, mock_ecs, _exec_event())
        second = mock_dynamodb.put_item.call_args_list[0].kwargs['Item']['worker_token_hash']['S']
        self.assertNotEqual(first, second)

    def test_scheduled_trigger_also_gets_token(self, mock_dynamodb, mock_ecs, _):
        event = _exec_event(trigger='Scheduled')
        del event['requestContext']  # EventBridge Scheduler invocation
        resp = self._run_ecs(mock_dynamodb, mock_ecs, event)
        self.assertEqual(resp['statusCode'], 200)
        self.assertIn('worker_token_hash', mock_dynamodb.put_item.call_args_list[0].kwargs['Item'])

    def test_ci_runner_has_no_worker_token(self, mock_dynamodb, mock_ecs, _):
        resp = self._run_ecs(mock_dynamodb, mock_ecs, _exec_event(trigger='ci_runner'))
        self.assertEqual(resp['statusCode'], 200)
        self.assertNotIn('worker_token_hash', mock_dynamodb.put_item.call_args_list[0].kwargs['Item'])
        mock_ecs.run_task.assert_not_called()

    def test_missing_execute_scope_403(self, mock_dynamodb, mock_ecs, _):
        resp = handler(_exec_event(scope='api/usecases.read api/executions.write'), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    def test_viewer_in_owner_team_403(self, mock_dynamodb, mock_ecs, _):
        resp = handler(_exec_event(team_roles=json.dumps([{'team_id': 'team-a', 'role': 'viewer'}])), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    @patch('resource_auth.list_shared_access', return_value=[])
    def test_other_team_403(self, _shares, mock_dynamodb, mock_ecs, _):
        resp = handler(_exec_event(team_roles=json.dumps([{'team_id': 'team-b', 'role': 'editor'}])), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    def test_orphan_usecase_denied(self, mock_dynamodb, mock_ecs, _):
        with patch('resource_auth.get_usecase_owner',
                   return_value={'application_id': None, 'owner_team_id': None, 'created_by': None}):
            resp = handler(_exec_event(team_roles=json.dumps([{'team_id': 'team-a', 'role': 'team_lead'}])), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    def test_unbound_client_denied_bound_client_allowed(self, mock_dynamodb, mock_ecs, _):
        with patch('resource_auth.list_shared_access', return_value=[]):
            resp = handler(_exec_event(trigger='ci_runner', identity_type='client', team_roles='[]'), None)
        self.assertEqual(resp['statusCode'], 403)
        resp = self._run_ecs(mock_dynamodb, mock_ecs, _exec_event(
            trigger='ci_runner', identity_type='client',
            team_roles=json.dumps([{'team_id': 'team-a', 'role': 'editor'}])))
        self.assertEqual(resp['statusCode'], 200)

    def test_worker_cannot_start_executions(self, mock_dynamodb, mock_ecs, _):
        resp = handler(_exec_event(identity_type='worker'), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

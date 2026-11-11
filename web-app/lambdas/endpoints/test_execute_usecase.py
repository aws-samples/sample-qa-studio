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


def _batch_written_items(mock_dynamodb):
    """Items persisted through ``batch_write_item`` (execution steps)."""
    return [
        request['PutRequest']['Item']
        for c in mock_dynamodb.batch_write_item.call_args_list
        for requests in c.kwargs['RequestItems'].values()
        for request in requests
    ]


def _without_sk(items):
    """Items minus their fresh UUIDv7 ``sk`` so two builds can be compared."""
    return [{k: v for k, v in item.items() if k != 'sk'} for item in items]


#: Env the worker stack gives execute_usecase for the MicroVM launch
#: (microvm_launch.launch_microvm + start_microvm_execution).
_MICROVM_ENV = {
    'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1', 'S3_BUCKET_PREFIX': 'b',
    'AWS_REGION': 'eu-central-1', 'USER_AGENT': 'qa-studio-ua',
    'MICROVM_IMAGE_ARN': 'arn:aws:lambda:eu-central-1:123456789012:microvm-image:test-worker',
    'MICROVM_IMAGE_VERSION': '3.0',
    'MICROVM_EXECUTION_ROLE_ARN': 'arn:aws:iam::123456789012:role/test-microvm-execution-role',
    'MICROVM_LOG_GROUP': '/qa-studio/test/microvm',
    'MAX_EXECUTION_DURATION_MINUTES': '45',
}


def _fake_microvm_client(run_microvm=None):
    """``lambda-microvms`` client stand-in; ``run_microvm`` may be a side effect."""
    client = MagicMock()
    client.meta.region_name = 'eu-central-1'
    if run_microvm is not None:
        client.run_microvm.side_effect = run_microvm
    else:
        client.run_microvm.return_value = {'microvmId': 'vm-123', 'state': 'PENDING'}
    return client


class TestExecuteUsecaseCiRunner(unittest.TestCase):
    """Test suite for execute_usecase Lambda with ci_runner trigger type"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['DEFAULT_REGION'] = 'us-east-1'
        os.environ['S3_BUCKET_PREFIX'] = 'test-bucket'
        os.environ['AWS_REGION'] = 'us-east-1'
        
    def test_ci_runner_creates_execution_record(self):
        """Test that ci_runner trigger creates execution record without a MicroVM"""
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
            
            # No MicroVM is launched for ci_runner (see TestExecuteUsecaseMicrovmRuntime.test_ci_runner_launches_nothing)
    
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
            step_items = [item for item in _batch_written_items(mock_dynamodb) if 'EXECUTION_STEP#' in item['sk']['S']]
            self.assertEqual(len(step_items), 2)
    
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


@patch.dict(os.environ, _MICROVM_ENV)
class TestExecuteUsecaseBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility for existing trigger types"""

    def _run(self, event, mock_dynamodb):
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'starting_url': {'S': 'https://example.com'},
                'executing_region': {'S': 'us-east-1'},
                'model_id': {'S': 'test-model'}
            }
        }
        mock_dynamodb.query.return_value = {'Items': []}
        client = _fake_microvm_client()
        with patch('microvm_launch.get_microvm_client', return_value=client):
            response = handler(event, None)
        return response, client

    def test_ondemand_trigger_rejected_before_any_write(self):
        """Use-case-level OnDemand was removed: 400 naming the valid values, nothing written."""
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
             patch('execute_usecase.eventbridge'):
            response, client = self._run(event, mock_dynamodb)

            self.assertEqual(response['statusCode'], 400)
            error = json.loads(response['body'])['error']
            self.assertIn('Invalid trigger type: OnDemand', error)
            for valid in ('OnDemandHeadless', 'Scheduled', 'ci_runner'):
                self.assertIn(valid, error)
            mock_dynamodb.put_item.assert_not_called()
            mock_dynamodb.transact_write_items.assert_not_called()
            mock_dynamodb.batch_write_item.assert_not_called()
            client.run_microvm.assert_not_called()

    def test_scheduled_trigger_launches_a_microvm(self):
        """Test that Scheduled trigger launches a worker MicroVM"""
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
             patch('execute_usecase.eventbridge'):
            response, client = self._run(event, mock_dynamodb)

            self.assertEqual(response['statusCode'], 200, response['body'])
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'microvm started')
            self.assertEqual(body['microvmId'], 'vm-123')
            client.run_microvm.assert_called_once()

    def test_ondemandheadless_trigger_launches_a_microvm(self):
        """Test that OnDemandHeadless trigger launches a worker MicroVM"""
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
             patch('execute_usecase.eventbridge'):
            response, client = self._run(event, mock_dynamodb)

            self.assertEqual(response['statusCode'], 200, response['body'])
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'microvm started')
            client.run_microvm.assert_called_once()

    def test_default_trigger_type_is_ondemand_headless(self):
        """Without trigger-type the use case runs headless (a MicroVM is launched)."""
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
             patch('execute_usecase.eventbridge'):
            response, client = self._run(event, mock_dynamodb)

            self.assertEqual(response['statusCode'], 200, response['body'])
            body = json.loads(response['body'])
            self.assertEqual(body['status'], 'microvm started')
            client.run_microvm.assert_called_once()
            execution_item = mock_dynamodb.put_item.call_args_list[0][1]['Item']
            self.assertEqual(execution_item['trigger_type']['S'], 'OnDemandHeadless')


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


class TestExecuteUsecaseRepeatExpansion(unittest.TestCase):
    """Repeat steps are unrolled into execution steps; bad repeats fail before any write."""

    def setUp(self):
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['DEFAULT_REGION'] = 'us-east-1'

    def _event(self):
        return {
            'pathParameters': {'id': 'uc-1'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {'authorizer': {'client_id': 'ci', 'scope': 'api/usecases.execute',
                                              'teamRoles': EXECUTOR_TEAM_A}},
        }

    def _repeat_steps(self, rows):
        return [
            {
                'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
                'instruction': {'S': 'Users'},
                'repeat_columns': {'L': [{'S': 'email'}]},
                'repeat_rows': {'L': [{'L': [{'S': r}]} for r in rows]},
            },
            {
                'id': {'S': 'c1'}, 'sort': {'N': '2'}, 'step_type': {'S': 'navigation'},
                'instruction': {'S': 'Type {{email}}'}, 'parent_step_id': {'S': 'r1'},
            },
            {
                'id': {'S': 'p1'}, 'sort': {'N': '3'}, 'step_type': {'S': 'validation'},
                'instruction': {'S': 'Done'},
            },
        ]

    def test_repeat_is_expanded(self):
        with patch('execute_usecase.dynamodb') as mock_dynamodb, patch('execute_usecase.eventbridge'):
            mock_dynamodb.get_item.return_value = {'Item': {
                'starting_url': {'S': 'https://example.com'},
                'executing_region': {'S': 'us-east-1'}, 'model_id': {'S': 'm'},
            }}
            mock_dynamodb.query.return_value = {'Items': self._repeat_steps(['a', 'b', 'c'])}
            response = handler(self._event(), None)

            self.assertEqual(response['statusCode'], 200, response['body'])
            items = _batch_written_items(mock_dynamodb)
            self.assertEqual([i['step_id']['S'] for i in items], ['c1', 'c1', 'c1', 'p1'])
            self.assertEqual([i['sort']['N'] for i in items], ['1', '2', '3', '4'])
            self.assertEqual(items[1]['repeat_row_index'], {'N': '2'})
            self.assertEqual(items[1]['repeat_row_total'], {'N': '3'})
            self.assertEqual(items[1]['repeat_label'], {'S': 'Users'})
            self.assertEqual(items[1]['row_variables']['M']['email'], {'S': 'b'})
            self.assertNotIn('repeat_row_index', items[3])

    def test_invalid_repeat_returns_400_before_any_write(self):
        with patch('execute_usecase.dynamodb') as mock_dynamodb, patch('execute_usecase.eventbridge') as mock_eb:
            mock_dynamodb.get_item.return_value = {'Item': {
                'starting_url': {'S': 'https://example.com'},
                'executing_region': {'S': 'us-east-1'}, 'model_id': {'S': 'm'},
            }}
            mock_dynamodb.query.return_value = {'Items': self._repeat_steps([])}
            response = handler(self._event(), None)

            self.assertEqual(response['statusCode'], 400)
            self.assertIn('has no rows', json.loads(response['body'])['error'])
            mock_dynamodb.put_item.assert_not_called()
            mock_dynamodb.batch_write_item.assert_not_called()
            mock_eb.put_events.assert_not_called()


class TestExecuteUsecaseDatasetOverride(unittest.TestCase):
    """``repeat_datasets`` in the body replaces stored rows for the labelled repeat."""

    def setUp(self):
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['DEFAULT_REGION'] = 'us-east-1'

    def _event(self, body=None, raw_body=None):
        event = {
            'pathParameters': {'id': 'uc-1'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {'authorizer': {'client_id': 'ci', 'scope': 'api/usecases.execute',
                                              'teamRoles': EXECUTOR_TEAM_A}},
        }
        if raw_body is not None:
            event['body'] = raw_body
        elif body is not None:
            event['body'] = json.dumps(body)
        return event

    def _steps(self):
        return [
            {
                'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
                'instruction': {'S': 'Users'},
                'repeat_columns': {'L': [{'S': 'email'}, {'S': 'role'}]},
                'repeat_rows': {'L': [{'L': [{'S': 'stored'}, {'S': 'x'}]}]},
            },
            {
                'id': {'S': 'c1'}, 'sort': {'N': '2'}, 'step_type': {'S': 'navigation'},
                'instruction': {'S': 'Type {{email}}'}, 'parent_step_id': {'S': 'r1'},
            },
            {
                'id': {'S': 'r2'}, 'sort': {'N': '3'}, 'step_type': {'S': 'repeat'},
                'instruction': {'S': 'Other'},
                'repeat_columns': {'L': [{'S': 'n'}]},
                'repeat_rows': {'L': [{'L': [{'S': 'keep'}]}]},
            },
            {
                'id': {'S': 'c2'}, 'sort': {'N': '4'}, 'step_type': {'S': 'navigation'},
                'instruction': {'S': '{{n}}'}, 'parent_step_id': {'S': 'r2'},
            },
        ]

    def _run(self, event):
        with patch('execute_usecase.dynamodb') as mock_dynamodb, patch('execute_usecase.eventbridge') as mock_eb:
            mock_dynamodb.get_item.return_value = {'Item': {
                'starting_url': {'S': 'https://example.com'},
                'executing_region': {'S': 'us-east-1'}, 'model_id': {'S': 'm'},
            }}
            mock_dynamodb.query.return_value = {'Items': self._steps()}
            response = handler(event, None)
            return response, mock_dynamodb, mock_eb

    def test_no_body_uses_stored_rows(self):
        response, ddb, _ = self._run(self._event())
        self.assertEqual(response['statusCode'], 200)
        items = _batch_written_items(ddb)
        self.assertEqual(items[0]['row_variables']['M']['email'], {'S': 'stored'})

    def test_empty_body_object_uses_stored_rows(self):
        response, ddb, _ = self._run(self._event(body={}))
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(_batch_written_items(ddb)[0]['row_variables']['M']['email'], {'S': 'stored'})

    def test_override_replaces_only_labelled_repeat(self):
        body = {'repeat_datasets': {'Users': {
            'columns': ['role', 'email'],
            'rows': [['admin', 'o1'], ['viewer', 'o2']],
        }}}
        response, ddb, _ = self._run(self._event(body=body))
        self.assertEqual(response['statusCode'], 200, response['body'])
        items = _batch_written_items(ddb)
        users = [i for i in items if i['repeat_label']['S'] == 'Users']
        other = [i for i in items if i['repeat_label']['S'] == 'Other']
        self.assertEqual([i['row_variables']['M']['email']['S'] for i in users], ['o1', 'o2'])
        self.assertEqual([i['row_variables']['M']['role']['S'] for i in users], ['admin', 'viewer'])
        self.assertEqual([i['row_variables']['M']['n']['S'] for i in other], ['keep'])

    def _assert_400_without_writes(self, event, fragment):
        response, ddb, mock_eb = self._run(event)
        self.assertEqual(response['statusCode'], 400, response['body'])
        self.assertIn(fragment, json.loads(response['body'])['error'])
        ddb.put_item.assert_not_called()
        ddb.batch_write_item.assert_not_called()
        mock_eb.put_events.assert_not_called()

    def test_unknown_label_is_400(self):
        body = {'repeat_datasets': {'Nope': {'columns': ['email', 'role'], 'rows': [['a', 'b']]}}}
        self._assert_400_without_writes(self._event(body=body), 'no repeat step with label "Nope"')

    def test_column_mismatch_is_400(self):
        body = {'repeat_datasets': {'Users': {'columns': ['email', 'team'], 'rows': [['a', 'b']]}}}
        self._assert_400_without_writes(self._event(body=body), 'do not match')

    def test_caps_exceeded_is_400(self):
        body = {'repeat_datasets': {'Users': {
            'columns': ['email', 'role'], 'rows': [['a', 'b']] * 101,
        }}}
        self._assert_400_without_writes(self._event(body=body), 'at most 100 rows')

    def test_malformed_json_is_400(self):
        self._assert_400_without_writes(self._event(raw_body='{not json'), 'Invalid JSON')

    def test_non_object_datasets_is_400(self):
        self._assert_400_without_writes(self._event(body={'repeat_datasets': []}), 'repeat_datasets must be an object')

    def test_dataset_missing_rows_is_400(self):
        body = {'repeat_datasets': {'Users': {'columns': ['email', 'role']}}}
        self._assert_400_without_writes(self._event(body=body), 'repeat_rows must be a list')


class TestExecuteUsecaseDatasetReference(unittest.TestCase):
    """Repeat steps with ``dataset_id`` are resolved from the use case's application before expansion."""

    _DATASET_RECORD = {
        'dataset_id': {'S': 'ds-1'}, 'name': {'S': 'customers'},
        'columns': {'L': [{'S': 'email'}]},
        'rows': {'L': [{'L': [{'S': 'a@x.test'}]}, {'L': [{'S': 'b@x.test'}]}]},
    }

    def setUp(self):
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['DEFAULT_REGION'] = 'us-east-1'

    def _event(self, body=None):
        event = {
            'pathParameters': {'id': 'uc-1'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {'authorizer': {'client_id': 'ci', 'scope': 'api/usecases.execute',
                                              'teamRoles': EXECUTOR_TEAM_A}},
        }
        if body is not None:
            event['body'] = json.dumps(body)
        return event

    @staticmethod
    def _dataset_steps(dataset_id='ds-1'):
        return [
            {
                'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
                'instruction': {'S': 'Users'}, 'dataset_id': {'S': dataset_id},
            },
            {
                'id': {'S': 'c1'}, 'sort': {'N': '2'}, 'step_type': {'S': 'navigation'},
                'instruction': {'S': 'Type {{email}}'}, 'parent_step_id': {'S': 'r1'},
            },
            {
                'id': {'S': 'p1'}, 'sort': {'N': '3'}, 'step_type': {'S': 'validation'},
                'instruction': {'S': 'Done'},
            },
        ]

    @staticmethod
    def _inline_steps():
        return [
            {
                'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
                'instruction': {'S': 'Users'},
                'repeat_columns': {'L': [{'S': 'email'}]},
                'repeat_rows': {'L': [{'L': [{'S': 'inline'}]}]},
            },
            {
                'id': {'S': 'c1'}, 'sort': {'N': '2'}, 'step_type': {'S': 'navigation'},
                'instruction': {'S': 'Type {{email}}'}, 'parent_step_id': {'S': 'r1'},
                'cached_steps': {'S': '[]'},
            },
            {
                'id': {'S': 'p1'}, 'sort': {'N': '3'}, 'step_type': {'S': 'validation'},
                'instruction': {'S': 'Done'}, 'validation_type': {'S': 'text'},
            },
        ]

    def _run(self, steps, records, event=None, application_id='app-1'):
        """``records``: {(pk, sk): typed item} for everything but the use case itself."""
        usecase = {'starting_url': {'S': 'https://example.com'}, 'executing_region': {'S': 'us-east-1'},
                   'model_id': {'S': 'm'}}
        if application_id:
            usecase['application_id'] = {'S': application_id}

        def get_item(**kwargs):
            pk, sk = kwargs['Key']['pk']['S'], kwargs['Key']['sk']['S']
            if pk == 'USECASES':
                return {'Item': usecase}
            item = records.get((pk, sk))
            return {'Item': item} if item is not None else {}

        with patch('execute_usecase.dynamodb') as mock_dynamodb, patch('execute_usecase.eventbridge') as mock_eb:
            mock_dynamodb.get_item.side_effect = get_item
            mock_dynamodb.query.return_value = {'Items': steps}
            response = handler(event or self._event(), None)
        read_keys = [(c.kwargs['Key']['pk']['S'], c.kwargs['Key']['sk']['S'])
                     for c in mock_dynamodb.get_item.call_args_list]
        return response, mock_dynamodb, mock_eb, read_keys

    def test_dataset_rows_are_expanded_into_execution_steps(self):
        response, ddb, _, read_keys = self._run(
            self._dataset_steps(), {('APPLICATION#app-1', 'DATASET#ds-1'): self._DATASET_RECORD},
        )
        self.assertEqual(response['statusCode'], 200, response['body'])
        items = _batch_written_items(ddb)
        self.assertEqual([i['step_id']['S'] for i in items], ['c1', 'c1', 'p1'])
        self.assertEqual([i['row_variables']['M']['email']['S'] for i in items[:2]], ['a@x.test', 'b@x.test'])
        self.assertEqual(items[0]['repeat_label'], {'S': 'Users'})
        self.assertEqual(items[0]['repeat_row_total'], {'N': '2'})
        for item in items:
            self.assertNotIn('dataset_id', item)
            self.assertNotIn('repeat_columns', item)
        self.assertEqual(read_keys.count(('APPLICATION#app-1', 'DATASET#ds-1')), 1)

    def test_missing_dataset_is_400_before_any_write(self):
        response, ddb, mock_eb, _ = self._run(self._dataset_steps('ds-missing'), {})
        self.assertEqual(response['statusCode'], 400, response['body'])
        self.assertEqual(json.loads(response['body']), {'error': 'dataset not found', 'dataset_id': 'ds-missing'})
        ddb.put_item.assert_not_called()
        ddb.batch_write_item.assert_not_called()
        mock_eb.put_events.assert_not_called()

    def test_usecase_without_application_cannot_resolve_and_reads_no_application_record(self):
        response, ddb, _, read_keys = self._run(
            self._dataset_steps(), {('APPLICATION#app-1', 'DATASET#ds-1'): self._DATASET_RECORD},
            application_id=None,
        )
        self.assertEqual(response['statusCode'], 400, response['body'])
        self.assertEqual(json.loads(response['body'])['dataset_id'], 'ds-1')
        self.assertFalse(any(pk.startswith('APPLICATION#') for pk, _ in read_keys))
        ddb.put_item.assert_not_called()

    def test_repeat_datasets_override_wins_over_application_dataset(self):
        body = {'repeat_datasets': {'Users': {'columns': ['email'], 'rows': [['o1'], ['o2'], ['o3']]}}}
        response, ddb, _, read_keys = self._run(
            self._dataset_steps(), {('APPLICATION#app-1', 'DATASET#ds-1'): self._DATASET_RECORD},
            event=self._event(body=body),
        )
        self.assertEqual(response['statusCode'], 200, response['body'])
        items = _batch_written_items(ddb)
        self.assertEqual([i['row_variables']['M']['email']['S'] for i in items[:3]], ['o1', 'o2', 'o3'])
        self.assertIn(('APPLICATION#app-1', 'DATASET#ds-1'), read_keys)

    def test_inline_repeat_reads_no_dataset_and_is_byte_identical_to_the_builder(self):
        from execution_steps import build_execution_step_items

        response, ddb, _, read_keys = self._run(self._inline_steps(), {})
        self.assertEqual(response['statusCode'], 200, response['body'])
        self.assertFalse(any(sk.startswith('DATASET#') for _, sk in read_keys))
        written = _batch_written_items(ddb)
        execution_id = json.loads(response['body'])['executionId']
        created_at = written[0]['created_at']['S']
        expected = build_execution_step_items(self._inline_steps(), execution_id, created_at)
        self.assertEqual(_without_sk(written), _without_sk(expected))
        self.assertEqual([i['row_variables']['M']['email']['S'] for i in written[:1]], ['inline'])


# ---------------------------------------------------------------------------
# H-2 / N-1: scope + execute check, worker capability token
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402
from run_payload import RunPayload  # noqa: E402


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


@patch.dict(os.environ, _MICROVM_ENV)
@patch('execute_usecase.eventbridge')
@patch('execute_usecase.dynamodb')
class TestExecuteUsecaseAuthz(unittest.TestCase):
    def _run(self, mock_dynamodb, event):
        """Run ``event`` against an owned use case; returns ``(response, fake microvm client)``."""
        mock_dynamodb.get_item.side_effect = lambda **kw: (
            _usecase_item() if kw['Key']['sk']['S'].startswith('USECASE#') else {})
        mock_dynamodb.query.return_value = {'Items': []}
        client = _fake_microvm_client()
        with patch('microvm_launch.get_microvm_client', return_value=client):
            response = handler(event, None)
        return response, client

    def test_token_hash_stored_and_token_injected(self, mock_dynamodb, _):
        resp, client = self._run(mock_dynamodb, _exec_event())
        self.assertEqual(resp['statusCode'], 200, resp['body'])
        item = mock_dynamodb.put_item.call_args_list[0].kwargs['Item']
        stored_hash = item['worker_token_hash']['S']
        payload = RunPayload.from_hook_payload(client.run_microvm.call_args.kwargs['runHookPayload'])
        token = payload.execution_token.get_secret_value()
        self.assertGreaterEqual(len(token), 40)
        self.assertEqual(hashlib.sha256(token.encode()).hexdigest(), stored_hash)
        self.assertNotIn(token, json.dumps(item))
        self.assertNotIn(token, resp['body'])

    def test_each_execution_gets_its_own_token(self, mock_dynamodb, _):
        self._run(mock_dynamodb, _exec_event())
        first = mock_dynamodb.put_item.call_args_list[0].kwargs['Item']['worker_token_hash']['S']
        mock_dynamodb.reset_mock()
        self._run(mock_dynamodb, _exec_event())
        second = mock_dynamodb.put_item.call_args_list[0].kwargs['Item']['worker_token_hash']['S']
        self.assertNotEqual(first, second)

    def test_scheduled_trigger_also_gets_token(self, mock_dynamodb, _):
        event = _exec_event(trigger='Scheduled')
        del event['requestContext']  # EventBridge Scheduler invocation
        resp, _client = self._run(mock_dynamodb, event)
        self.assertEqual(resp['statusCode'], 200, resp['body'])
        self.assertIn('worker_token_hash', mock_dynamodb.put_item.call_args_list[0].kwargs['Item'])

    def test_ci_runner_has_no_worker_token(self, mock_dynamodb, _):
        resp, client = self._run(mock_dynamodb, _exec_event(trigger='ci_runner'))
        self.assertEqual(resp['statusCode'], 200)
        self.assertNotIn('worker_token_hash', mock_dynamodb.put_item.call_args_list[0].kwargs['Item'])
        client.run_microvm.assert_not_called()

    def test_missing_execute_scope_403(self, mock_dynamodb, _):
        resp = handler(_exec_event(scope='api/usecases.read api/executions.write'), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    def test_viewer_in_owner_team_403(self, mock_dynamodb, _):
        resp = handler(_exec_event(team_roles=json.dumps([{'team_id': 'team-a', 'role': 'viewer'}])), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    @patch('resource_auth.list_shared_access', return_value=[])
    def test_other_team_403(self, _shares, mock_dynamodb, _):
        resp = handler(_exec_event(team_roles=json.dumps([{'team_id': 'team-b', 'role': 'editor'}])), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    def test_orphan_usecase_denied(self, mock_dynamodb, _):
        with patch('resource_auth.get_usecase_owner',
                   return_value={'application_id': None, 'owner_team_id': None, 'created_by': None}):
            resp = handler(_exec_event(team_roles=json.dumps([{'team_id': 'team-a', 'role': 'team_lead'}])), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()

    def test_unbound_client_denied_bound_client_allowed(self, mock_dynamodb, _):
        with patch('resource_auth.list_shared_access', return_value=[]):
            resp = handler(_exec_event(trigger='ci_runner', identity_type='client', team_roles='[]'), None)
        self.assertEqual(resp['statusCode'], 403)
        resp, _client = self._run(mock_dynamodb, _exec_event(
            trigger='ci_runner', identity_type='client',
            team_roles=json.dumps([{'team_id': 'team-a', 'role': 'editor'}])))
        self.assertEqual(resp['statusCode'], 200)

    def test_worker_cannot_start_executions(self, mock_dynamodb, _):
        resp = handler(_exec_event(identity_type='worker'), None)
        self.assertEqual(resp['statusCode'], 403)
        mock_dynamodb.put_item.assert_not_called()


# ---------------------------------------------------------------------------
# Effective variables: the EXECUTION_VARIABLES snapshot carries the
# application layer merged under the use-case layer (no ``source``).
# ---------------------------------------------------------------------------

def _typed_rows(*pairs):
    return {'L': [{'M': {'key': {'S': k}, 'value': {'S': v}}} for k, v in pairs]}


class TestExecuteUsecaseEffectiveVariables(unittest.TestCase):
    def setUp(self):
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['DEFAULT_REGION'] = 'us-east-1'

    def _event(self):
        return {
            'pathParameters': {'id': 'uc-1'},
            'queryStringParameters': {'trigger-type': 'ci_runner'},
            'requestContext': {'authorizer': {'client_id': 'ci', 'scope': 'api/usecases.execute',
                                              'teamRoles': EXECUTOR_TEAM_A}},
        }

    def _run(self, records, usecase_extra=None):
        """``records``: {(pk, sk): typed item} for the variable layers."""
        usecase = {'starting_url': {'S': 'https://example.com'}, 'executing_region': {'S': 'us-east-1'},
                   'model_id': {'S': 'm'}, **(usecase_extra or {})}

        def get_item(**kwargs):
            pk, sk = kwargs['Key']['pk']['S'], kwargs['Key']['sk']['S']
            if pk == 'USECASES':
                return {'Item': usecase}
            item = records.get((pk, sk))
            return {'Item': item} if item is not None else {}

        with patch('execute_usecase.dynamodb') as mock_dynamodb, patch('execute_usecase.eventbridge'):
            mock_dynamodb.get_item.side_effect = get_item
            mock_dynamodb.query.return_value = {'Items': []}
            response = handler(self._event(), None)
        self.assertEqual(response['statusCode'], 200, response['body'])
        snapshots = [c.kwargs['Item'] for c in mock_dynamodb.put_item.call_args_list
                     if c.kwargs['Item']['sk']['S'] == 'EXECUTION_VARIABLES']
        read_keys = [(c.kwargs['Key']['pk']['S'], c.kwargs['Key']['sk']['S'])
                     for c in mock_dynamodb.get_item.call_args_list]
        return snapshots, read_keys

    def test_application_rows_merged_under_usecase_rows(self):
        snapshots, read_keys = self._run(
            {('APPLICATION#app-1', 'VARIABLES'): {'variables': _typed_rows(('zone', 'eu'), ('base', 'app'))},
             ('USECASE#uc-1', 'USECASE_VARIABLES'): {'variables': _typed_rows(('base', 'uc'), ('user', 'qa'))}},
            usecase_extra={'application_id': {'S': 'app-1'}},
        )
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['variables'], _typed_rows(('zone', 'eu'), ('base', 'uc'), ('user', 'qa')))
        self.assertNotIn('source', json.dumps(snapshots[0]))
        self.assertIn(('APPLICATION#app-1', 'VARIABLES'), read_keys)
        self.assertEqual(read_keys.count(('APPLICATION#app-1', 'VARIABLES')), 1)

    def test_application_only_is_snapshotted(self):
        snapshots, _ = self._run(
            {('APPLICATION#app-1', 'VARIABLES'): {'variables': _typed_rows(('a', '1'))}},
            usecase_extra={'application_id': {'S': 'app-1'}},
        )
        self.assertEqual(snapshots[0]['variables'], _typed_rows(('a', '1')))

    def test_legacy_usecase_without_application_is_byte_identical(self):
        stored = _typed_rows(('b', '2'), ('a', '1'))
        snapshots, read_keys = self._run({('USECASE#uc-1', 'USECASE_VARIABLES'): {'variables': stored}})
        self.assertEqual(snapshots[0]['variables'], stored)
        self.assertFalse(any(pk.startswith('APPLICATION#') for pk, _ in read_keys))

    def test_no_variables_anywhere_writes_no_snapshot(self):
        snapshots, _ = self._run({}, usecase_extra={'application_id': {'S': 'app-1'}})
        self.assertEqual(snapshots, [])


# ---------------------------------------------------------------------------
# MicroVM runtime: Scheduled / OnDemandHeadless launch a Lambda MicroVM with
# the per-execution RunPayload; ci_runner launches nothing.
# ---------------------------------------------------------------------------

from botocore.exceptions import ClientError  # noqa: E402

_MOBILE_USECASE_FIELDS = {
    'test_platform': 'mobile', 'platform': 'ANDROID', 'app_package': 'com.example.app',
    'app_activity': '.MainActivity', 'app_binary_s3_path': 's3://b/app.apk',
    'device_farm_project_arn': 'arn:aws:devicefarm:us-west-2:1:project:p', 'device_arn': 'arn:aws:devicefarm:us-west-2::device:d',
}


def _throttling_error():
    return ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'slow down'}}, 'RunMicrovm')


@patch.dict(os.environ, _MICROVM_ENV)
@patch('execute_usecase.eventbridge')
@patch('execute_usecase.dynamodb')
class TestExecuteUsecaseMicrovmRuntime(unittest.TestCase):
    def _run(self, mock_dynamodb, event=None, usecase_extra=None, run_microvm=None):
        usecase = {'starting_url': {'S': 'https://example.com'}, 'executing_region': {'S': 'us-west-2'},
                   'model_id': {'S': 'm'}, 'application_id': {'S': 'app-1'}}
        for key, value in (usecase_extra or {}).items():
            usecase[key] = {'S': value}
        mock_dynamodb.get_item.side_effect = lambda **kw: (
            {'Item': usecase} if kw['Key']['sk']['S'].startswith('USECASE#') else {})
        mock_dynamodb.query.return_value = {'Items': []}
        client = _fake_microvm_client(run_microvm)
        with patch('microvm_launch.get_microvm_client', return_value=client), \
             patch('microvm_launch.time.sleep') as sleep:
            response = handler(event or _exec_event(), None)
        return response, client, sleep

    @staticmethod
    def _execution_updates(mock_dynamodb):
        return [c.kwargs for c in mock_dynamodb.update_item.call_args_list]

    def test_launches_a_microvm(self, mock_dynamodb, _):
        response, client, _sleep = self._run(mock_dynamodb)

        self.assertEqual(response['statusCode'], 200, response['body'])
        body = json.loads(response['body'])
        self.assertEqual(body['status'], 'microvm started')
        self.assertEqual(body['usecaseId'], 'uc-1')
        self.assertEqual(body['microvmId'], 'vm-123')
        self.assertIn('executionId', body)
        self.assertEqual(
            body['cloudWatchLogsUrl'],
            'https://eu-central-1.console.aws.amazon.com/cloudwatch/home?region=eu-central-1'
            f"#logsV2:log-groups/log-group//qa-studio/test/microvm/log-events/{body['executionId']}",
        )
        self.assertNotIn('taskArn', body)
        client.run_microvm.assert_called_once()

    def test_run_microvm_parameters(self, mock_dynamodb, _):
        response, client, _sleep = self._run(mock_dynamodb)
        execution_id = json.loads(response['body'])['executionId']
        kwargs = client.run_microvm.call_args.kwargs

        self.assertEqual(kwargs['imageIdentifier'], _MICROVM_ENV['MICROVM_IMAGE_ARN'])
        self.assertEqual(kwargs['imageVersion'], '3.0')
        self.assertEqual(kwargs['executionRoleArn'], _MICROVM_ENV['MICROVM_EXECUTION_ROLE_ARN'])
        self.assertEqual(kwargs['ingressNetworkConnectors'],
                         ['arn:aws:lambda:eu-central-1:aws:network-connector:aws-network-connector:NO_INGRESS'])
        self.assertNotIn('egressNetworkConnectors', kwargs)
        self.assertEqual(kwargs['idlePolicy'],
                         {'maxIdleDurationSeconds': 2700, 'suspendedDurationSeconds': 0, 'autoResumeEnabled': False})
        self.assertEqual(kwargs['logging'],
                         {'cloudWatch': {'logGroup': '/qa-studio/test/microvm', 'logStream': execution_id}})
        self.assertEqual(kwargs['maximumDurationInSeconds'], 45 * 60)
        self.assertEqual(kwargs['clientToken'], execution_id)

    def test_web_payload_carries_the_per_execution_values(self, mock_dynamodb, _):
        response, client, _sleep = self._run(mock_dynamodb)
        execution_id = json.loads(response['body'])['executionId']
        payload = RunPayload.from_hook_payload(client.run_microvm.call_args.kwargs['runHookPayload'])

        self.assertEqual(payload.mode, 'batch')
        self.assertEqual(payload.usecase_id, 'uc-1')
        self.assertEqual(payload.execution_id, execution_id)
        self.assertIsNone(payload.session_id)
        # executing region of the use case, not the stack region
        self.assertEqual(payload.region, 'us-west-2')
        self.assertEqual(payload.s3_bucket, 'b-us-west-2')
        self.assertEqual(payload.user_agent, 'qa-studio-ua')
        self.assertEqual(payload.max_duration_s, 45 * 60)
        self.assertIsNone(payload.mobile)

    def test_payload_token_matches_the_stored_hash_and_is_never_persisted(self, mock_dynamodb, _):
        response, client, _sleep = self._run(mock_dynamodb)
        payload = RunPayload.from_hook_payload(client.run_microvm.call_args.kwargs['runHookPayload'])
        token = payload.execution_token.get_secret_value()
        item = mock_dynamodb.put_item.call_args_list[0].kwargs['Item']

        self.assertGreaterEqual(len(token), 40)
        self.assertEqual(hashlib.sha256(token.encode()).hexdigest(), item['worker_token_hash']['S'])
        self.assertNotIn(token, json.dumps(item))
        self.assertNotIn(token, response['body'])
        self.assertNotIn(token, json.dumps(self._execution_updates(mock_dynamodb)))

    def test_mobile_payload_uses_the_use_case_mobile_fields(self, mock_dynamodb, _):
        response, client, _sleep = self._run(mock_dynamodb, usecase_extra=_MOBILE_USECASE_FIELDS)
        self.assertEqual(response['statusCode'], 200, response['body'])
        payload = RunPayload.from_hook_payload(client.run_microvm.call_args.kwargs['runHookPayload'])

        self.assertIsNotNone(payload.mobile)
        self.assertEqual(payload.mobile.model_dump(exclude_none=True), _MOBILE_USECASE_FIELDS)
        # the env the supervisor exports to the runner (non-empty fields, upper-cased)
        self.assertEqual(payload.mobile.to_env(), {k.upper(): v for k, v in _MOBILE_USECASE_FIELDS.items()})

    def test_execution_record_gets_microvm_id_and_logs_url_but_no_task_fields(self, mock_dynamodb, _):
        response, _client, _sleep = self._run(mock_dynamodb)
        body = json.loads(response['body'])
        updates = self._execution_updates(mock_dynamodb)

        self.assertEqual(len(updates), 1)
        update = updates[0]
        self.assertEqual(update['Key'], {'pk': {'S': 'USECASE_EXECUTION#uc-1'},
                                         'sk': {'S': f"EXECUTION#{body['executionId']}"}})
        self.assertEqual(update['ExpressionAttributeValues'][':microvm_id'], {'S': 'vm-123'})
        self.assertEqual(update['ExpressionAttributeValues'][':cloudwatch_url'], {'S': body['cloudWatchLogsUrl']})
        self.assertIn('microvm_id', update['UpdateExpression'])
        self.assertIn('cloudwatch_logs_url', update['UpdateExpression'])
        self.assertNotIn('task_arn', update['UpdateExpression'])
        self.assertNotIn('task_id', update['UpdateExpression'])
        self.assertNotIn('status', update['UpdateExpression'])

    def test_throttling_is_retried_five_times_then_succeeds(self, mock_dynamodb, _):
        response, client, sleep = self._run(
            mock_dynamodb, run_microvm=[_throttling_error()] * 4 + [{'microvmId': 'vm-late'}])

        self.assertEqual(response['statusCode'], 200, response['body'])
        self.assertEqual(json.loads(response['body'])['microvmId'], 'vm-late')
        self.assertEqual(client.run_microvm.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
        self.assertEqual(self._execution_updates(mock_dynamodb)[0]['ExpressionAttributeValues'][':microvm_id'],
                         {'S': 'vm-late'})

    def test_throttling_beyond_the_retries_marks_failed_and_returns_500(self, mock_dynamodb, _):
        response, client, _sleep = self._run(mock_dynamodb, run_microvm=_throttling_error())

        self.assertEqual(response['statusCode'], 500)
        self.assertEqual(client.run_microvm.call_count, 5)
        self.assertIn('Failed to start MicroVM', json.loads(response['body'])['error'])
        updates = self._execution_updates(mock_dynamodb)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]['ExpressionAttributeValues'][':status'], {'S': 'failed'})
        self.assertIn('ThrottlingException', updates[0]['ExpressionAttributeValues'][':error_msg']['S'])

    def test_non_throttling_error_is_not_retried_and_fails_the_execution(self, mock_dynamodb, mock_eb):
        error = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'RunMicrovm')
        response, client, sleep = self._run(mock_dynamodb, run_microvm=error)

        self.assertEqual(response['statusCode'], 500)
        self.assertEqual(client.run_microvm.call_count, 1)
        sleep.assert_not_called()
        updates = self._execution_updates(mock_dynamodb)
        self.assertEqual(updates[0]['ExpressionAttributeValues'][':status'], {'S': 'failed'})
        self.assertIn('AccessDeniedException', updates[0]['ExpressionAttributeValues'][':error_msg']['S'])
        statuses = [json.loads(e['Detail'])['status'] for c in mock_eb.put_events.call_args_list
                    for e in c.kwargs['Entries']]
        self.assertEqual(statuses, ['pending', 'failed'])

    def test_oversized_payload_fails_before_any_launch(self, mock_dynamodb, _):
        with patch.dict(os.environ, {'USER_AGENT': 'x' * 5000}):
            response, client, _sleep = self._run(mock_dynamodb)

        self.assertEqual(response['statusCode'], 500)
        client.run_microvm.assert_not_called()
        self.assertIn('4096', json.loads(response['body'])['error'])
        self.assertEqual(self._execution_updates(mock_dynamodb)[0]['ExpressionAttributeValues'][':status'],
                         {'S': 'failed'})

    def test_scheduled_trigger_also_uses_the_microvm(self, mock_dynamodb, _):
        event = _exec_event(trigger='Scheduled')
        del event['requestContext']  # EventBridge Scheduler invocation
        response, client, _sleep = self._run(mock_dynamodb, event=event)
        self.assertEqual(response['statusCode'], 200, response['body'])
        client.run_microvm.assert_called_once()

    def test_ci_runner_launches_nothing(self, mock_dynamodb, _):
        response, client, _sleep = self._run(mock_dynamodb, event=_exec_event(trigger='ci_runner'))
        self.assertEqual(response['statusCode'], 200, response['body'])
        self.assertEqual(json.loads(response['body'])['status'], 'execution created')
        client.run_microvm.assert_not_called()


# ---------------------------------------------------------------------------
# RUNNING_EXECUTIONS tracking record: written right after a successful MicroVM
# launch (never for ci_runner, never when the launch fails).
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402


def _running_execution_puts(mock_dynamodb):
    return [c.kwargs['Item'] for c in mock_dynamodb.put_item.call_args_list
            if c.kwargs['Item']['pk'] == {'S': 'RUNNING_EXECUTIONS'}]


def _parse_ts(value):
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


@patch.dict(os.environ, _MICROVM_ENV)
@patch('execute_usecase.eventbridge')
@patch('execute_usecase.dynamodb')
class TestExecuteUsecaseRunningExecutionRecord(unittest.TestCase):
    """Same MicroVM harness as ``TestExecuteUsecaseMicrovmRuntime`` (helpers borrowed, not subclassed:
    a subclass would be patched twice by the class decorators)."""

    _run = TestExecuteUsecaseMicrovmRuntime._run
    _execution_updates = staticmethod(TestExecuteUsecaseMicrovmRuntime._execution_updates)

    def test_running_execution_record_is_written_after_the_launch(self, mock_dynamodb, _):
        response, _client, _sleep = self._run(mock_dynamodb)
        execution_id = json.loads(response['body'])['executionId']

        puts = _running_execution_puts(mock_dynamodb)
        self.assertEqual(len(puts), 1)
        item = puts[0]
        self.assertEqual(item['sk'], {'S': f'EXECUTION#{execution_id}'})
        self.assertEqual(item['usecase_id'], {'S': 'uc-1'})
        self.assertEqual(item['microvm_id'], {'S': 'vm-123'})
        self.assertEqual(item['mode'], {'S': 'batch'})
        self.assertNotIn('suite_execution_id', item)
        # deadline = started_at + MAX_EXECUTION_DURATION_MINUTES (45) + 10 min grace
        started = _parse_ts(item['started_at']['S'])
        deadline = _parse_ts(item['deadline']['S'])
        self.assertEqual((deadline - started).total_seconds(), 45 * 60 + 10 * 60)
        self.assertLessEqual(abs((datetime.now(timezone.utc) - started).total_seconds()), 5)

        # written AFTER the execution record got its microvm_id
        order = [c[0] for c in mock_dynamodb.method_calls if c[0] in ('update_item', 'put_item')]
        self.assertEqual(order.index('update_item'), len(order) - 2)
        self.assertEqual(order[-1], 'put_item')

    def test_running_execution_record_carries_the_suite_execution_id(self, mock_dynamodb, _):
        event = _exec_event()
        event['queryStringParameters'].update({'suite-execution-id': 'se-9', 'suite-id': 's-9'})
        response, _client, _sleep = self._run(mock_dynamodb, event=event)
        self.assertEqual(response['statusCode'], 200, response['body'])

        item = _running_execution_puts(mock_dynamodb)[0]
        self.assertEqual(item['suite_execution_id'], {'S': 'se-9'})

    def test_failed_launch_writes_no_running_execution_record(self, mock_dynamodb, _):
        error = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'RunMicrovm')
        response, _client, _sleep = self._run(mock_dynamodb, run_microvm=error)
        self.assertEqual(response['statusCode'], 500)
        self.assertEqual(_running_execution_puts(mock_dynamodb), [])

    def test_running_execution_write_failure_does_not_fail_the_launch(self, mock_dynamodb, _):
        def put_item(**kwargs):
            if kwargs['Item']['pk'] == {'S': 'RUNNING_EXECUTIONS'}:
                raise ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'slow'}},
                                  'PutItem')
            return {}
        mock_dynamodb.put_item.side_effect = put_item

        response, _client, _sleep = self._run(mock_dynamodb)

        self.assertEqual(response['statusCode'], 200, response['body'])
        self.assertEqual(json.loads(response['body'])['microvmId'], 'vm-123')
        # the execution was not marked failed
        statuses = [u['ExpressionAttributeValues'].get(':status') for u in self._execution_updates(mock_dynamodb)]
        self.assertNotIn({'S': 'failed'}, statuses)

    def test_ci_runner_writes_no_running_execution_record(self, mock_dynamodb, _):
        self._run(mock_dynamodb, event=_exec_event(trigger='ci_runner'))
        self.assertEqual(_running_execution_puts(mock_dynamodb), [])

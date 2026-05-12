import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from update_execution_step_status import handler


class TestUpdateExecutionStepStatusSuccess(unittest.TestCase):
    """Test successful step status updates"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        
    def test_valid_status_update(self):
        """Test updating step status with valid data"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            # Mock execution exists
            mock_dynamodb.get_item.side_effect = [
                {'Item': {'pk': {'S': 'USECASE_EXECUTION#usecase-123'}}},  # Execution
                {'Item': {'pk': {'S': 'EXECUTION#execution-456'}}}  # Step
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertTrue(body['success'])
            self.assertEqual(body['step_id'], 'step-789')
            self.assertEqual(body['status'], 'running')
            
            # Verify update was called
            mock_dynamodb.update_item.assert_called_once()
            update_call = mock_dynamodb.update_item.call_args[1]
            self.assertIn('status', update_call['UpdateExpression'])
    
    def test_status_update_with_started_at(self):
        """Test updating step status with started_at timestamp"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'running',
                'started_at': '2024-01-15T10:30:00Z'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},  # Execution exists
                {'Item': {}}   # Step exists
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            # Verify started_at was included in update
            update_call = mock_dynamodb.update_item.call_args[1]
            self.assertIn('started_at', update_call['UpdateExpression'])
            self.assertIn(':started_at', update_call['ExpressionAttributeValues'])
    
    def test_status_update_with_completed_at(self):
        """Test updating step status with completed_at timestamp"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'completed',
                'completed_at': '2024-01-15T10:35:00Z'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            # Verify completed_at was included
            update_call = mock_dynamodb.update_item.call_args[1]
            self.assertIn('completed_at', update_call['UpdateExpression'])
    
    def test_status_update_with_error_message(self):
        """Test updating step status with error message"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'failed',
                'error_message': 'Element not found'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            # Verify error_message was included
            update_call = mock_dynamodb.update_item.call_args[1]
            self.assertIn('error_message', update_call['UpdateExpression'])
    
    def test_all_status_values(self):
        """Test all valid status values"""
        valid_statuses = ['pending', 'running', 'completed', 'failed', 'skipped', 'success']
        
        for status in valid_statuses:
            with self.subTest(status=status):
                event = {
                    'pathParameters': {
                        'id': 'usecase-123',
                        'executionId': 'execution-456',
                        'stepId': 'step-789'
                    },
                    'body': json.dumps({'status': status}),
                    'requestContext': {
                        'authorizer': {
                            'client_id': 'ci-runner-client',
                            'scope': 'api/executions.write'
                        }
                    }
                }
                
                with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
                    mock_dynamodb.get_item.side_effect = [
                        {'Item': {}},
                        {'Item': {}}
                    ]
                    
                    response = handler(event, None)
                    
                    self.assertEqual(response['statusCode'], 200)
                    body = json.loads(response['body'])
                    self.assertEqual(body['status'], status)

    def test_status_update_with_actual_value(self):
        """Test updating step status with actual_value for validation steps"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'success',
                'actual_value': 'Order #12345'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            update_call = mock_dynamodb.update_item.call_args[1]
            self.assertIn('actual_value', update_call['UpdateExpression'])
            self.assertEqual(
                update_call['ExpressionAttributeValues'][':actual_value'],
                {'S': 'Order #12345'}
            )

    def test_status_update_with_act_id(self):
        """Test updating step status with act_id for Nova Act trace linking"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'success',
                'act_id': 'act-abc-123'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            update_call = mock_dynamodb.update_item.call_args[1]
            self.assertIn('act_id', update_call['UpdateExpression'])
            self.assertEqual(
                update_call['ExpressionAttributeValues'][':act_id'],
                {'S': 'act-abc-123'}
            )

    def test_status_update_with_logs(self):
        """Test updating step status with logs"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'failed',
                'logs': 'Element not found after 30s timeout'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            update_call = mock_dynamodb.update_item.call_args[1]
            self.assertIn('#logs', update_call['UpdateExpression'])
            self.assertEqual(
                update_call['ExpressionAttributeNames']['#logs'],
                'logs'
            )
            self.assertEqual(
                update_call['ExpressionAttributeValues'][':logs'],
                {'S': 'Element not found after 30s timeout'}
            )

    def test_status_update_with_all_new_fields(self):
        """Test updating step status with all new fields together"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'success',
                'actual_value': 'Welcome, User',
                'act_id': 'act-xyz-789',
                'logs': 'Step completed successfully',
                'started_at': '2024-01-15T10:30:00Z',
                'completed_at': '2024-01-15T10:30:05Z'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            update_call = mock_dynamodb.update_item.call_args[1]
            expr = update_call['UpdateExpression']
            self.assertIn('actual_value', expr)
            self.assertIn('act_id', expr)
            self.assertIn('#logs', expr)
            self.assertIn('started_at', expr)
            self.assertIn('completed_at', expr)

    def test_new_fields_are_optional(self):
        """Test that actual_value, act_id, and logs are optional (backward compatible)"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            
            update_call = mock_dynamodb.update_item.call_args[1]
            expr = update_call['UpdateExpression']
            # None of the new fields should be in the expression when not provided
            self.assertNotIn('actual_value', expr)
            self.assertNotIn('act_id', expr)
            self.assertNotIn('#logs', expr)


class TestUpdateExecutionStepStatusErrors(unittest.TestCase):
    """Test error cases for step status updates"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        
    def test_invalid_status_returns_400(self):
        """Test that invalid status value returns 400"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'invalid_status'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid status', body['error'])
        self.assertIn('invalid_status', body['error'])
    
    def test_execution_not_found_returns_404(self):
        """Test that non-existent execution returns 404"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'non-existent',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            # Execution not found
            mock_dynamodb.get_item.return_value = {}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 404)
            body = json.loads(response['body'])
            self.assertIn('Execution not found', body['error'])
    
    def test_step_not_found_returns_404(self):
        """Test that non-existent step returns 404"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'non-existent'
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            # Execution exists, step doesn't
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},  # Execution found
                {}             # Step not found
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 404)
            body = json.loads(response['body'])
            self.assertIn('Step not found', body['error'])
    
    def test_missing_status_field_returns_400(self):
        """Test that missing status field returns 400"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'started_at': '2024-01-15T10:30:00Z'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing required field: status', body['error'])
    
    def test_missing_path_parameters_returns_400(self):
        """Test that missing path parameters returns 400"""
        event = {
            'pathParameters': {
                'id': 'usecase-123'
                # Missing executionId and stepId
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('is required', body['error'])
    
    def test_invalid_json_returns_400(self):
        """Test that invalid JSON returns 400"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': 'not valid json',
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid JSON', body['error'])
    
    def test_insufficient_permissions_returns_403(self):
        """Test that missing api/execution.write scope returns 403"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/usecases.read'  # Wrong scope
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])
    
    def test_admin_scope_grants_access(self):
        """Test that api/admin scope grants access"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'admin@example.com',
                    'sub': 'admin-123',
                    'scope': 'api/admin'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = [
                {'Item': {}},
                {'Item': {}}
            ]
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
    
    def test_dynamodb_error_returns_500(self):
        """Test that DynamoDB errors return 500"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'status': 'running'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        with patch('update_execution_step_status.dynamodb') as mock_dynamodb:
            mock_dynamodb.get_item.side_effect = Exception('DynamoDB error')
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 500)
            body = json.loads(response['body'])
            self.assertIn('Failed to update step status', body['error'])


if __name__ == '__main__':
    unittest.main()


class TestClearCacheFields(unittest.TestCase):
    """R-API-6: extend status update to remove stale cache fields.

    The primary update lives on ``EXECUTION#{exec}/EXECUTION_STEP#{step}``;
    the cache fields live on ``USECASE#{uc}/STEP#{step}``.  The handler
    does two separate UpdateItem calls — the second is best-effort.
    """

    def setUp(self):
        os.environ['TABLE_NAME'] = 'test-table'

    def _event(self, body):
        return {
            'pathParameters': {
                'id': 'uc-1',
                'executionId': 'exec-1',
                'stepId': 'step-1',
            },
            'body': json.dumps(body),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci',
                    'scope': 'api/executions.write',
                },
            },
        }

    def test_clear_fields_invokes_second_update(self):
        event = self._event({
            'status': 'failed',
            'clear_cache_fields': [
                'trajectory_s3_key', 'trajectory_last_updated',
            ],
        })

        with patch('update_execution_step_status.dynamodb') as mock_ddb:
            mock_ddb.get_item.side_effect = [
                {'Item': {'pk': {'S': 'USECASE_EXECUTION#uc-1'}}},
                {'Item': {'pk': {'S': 'EXECUTION#exec-1'}}},
            ]
            response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        # First update = step status; second update = cache REMOVE.
        self.assertEqual(mock_ddb.update_item.call_count, 2)
        cleanup_kwargs = mock_ddb.update_item.call_args_list[1].kwargs
        self.assertEqual(cleanup_kwargs['Key']['pk']['S'], 'USECASE#uc-1')
        self.assertEqual(cleanup_kwargs['Key']['sk']['S'], 'STEP#step-1')
        expr = cleanup_kwargs['UpdateExpression']
        self.assertTrue(expr.startswith('REMOVE '))
        self.assertIn('trajectory_s3_key', expr)
        self.assertIn('trajectory_last_updated', expr)

    def test_clear_fields_omitted_only_updates_status(self):
        event = self._event({'status': 'running'})

        with patch('update_execution_step_status.dynamodb') as mock_ddb:
            mock_ddb.get_item.side_effect = [
                {'Item': {'pk': {'S': 'USECASE_EXECUTION#uc-1'}}},
                {'Item': {'pk': {'S': 'EXECUTION#exec-1'}}},
            ]
            response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(mock_ddb.update_item.call_count, 1)

    def test_empty_clear_fields_list_is_noop(self):
        event = self._event({
            'status': 'running', 'clear_cache_fields': [],
        })

        with patch('update_execution_step_status.dynamodb') as mock_ddb:
            mock_ddb.get_item.side_effect = [
                {'Item': {'pk': {'S': 'USECASE_EXECUTION#uc-1'}}},
                {'Item': {'pk': {'S': 'EXECUTION#exec-1'}}},
            ]
            response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        # No REMOVE call when list is empty.
        self.assertEqual(mock_ddb.update_item.call_count, 1)

    def test_unknown_field_rejected(self):
        event = self._event({
            'status': 'running',
            'clear_cache_fields': ['trajectory_s3_key', 'arbitrary_attr'],
        })

        with patch('update_execution_step_status.dynamodb') as mock_ddb:
            response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        self.assertIn('arbitrary_attr', json.loads(response['body'])['error'])
        mock_ddb.update_item.assert_not_called()

    def test_non_list_rejected(self):
        event = self._event({
            'status': 'running',
            'clear_cache_fields': 'trajectory_s3_key',
        })

        with patch('update_execution_step_status.dynamodb'):
            response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)

    def test_non_string_elements_rejected(self):
        event = self._event({
            'status': 'running',
            'clear_cache_fields': ['trajectory_s3_key', 123],
        })

        with patch('update_execution_step_status.dynamodb'):
            response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)

    def test_duplicate_fields_deduplicated(self):
        event = self._event({
            'status': 'running',
            'clear_cache_fields': [
                'trajectory_s3_key', 'trajectory_s3_key', 'cached_steps',
            ],
        })

        with patch('update_execution_step_status.dynamodb') as mock_ddb:
            mock_ddb.get_item.side_effect = [
                {'Item': {'pk': {'S': 'USECASE_EXECUTION#uc-1'}}},
                {'Item': {'pk': {'S': 'EXECUTION#exec-1'}}},
            ]
            response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        cleanup_kwargs = mock_ddb.update_item.call_args_list[1].kwargs
        expr = cleanup_kwargs['UpdateExpression']
        # trajectory_s3_key appears once, cached_steps once.
        self.assertEqual(expr.count('trajectory_s3_key'), 1)
        self.assertEqual(expr.count('cached_steps'), 1)

    def test_cleanup_failure_does_not_fail_status_update(self):
        event = self._event({
            'status': 'failed',
            'clear_cache_fields': ['trajectory_s3_key'],
        })

        with patch('update_execution_step_status.dynamodb') as mock_ddb:
            mock_ddb.get_item.side_effect = [
                {'Item': {'pk': {'S': 'USECASE_EXECUTION#uc-1'}}},
                {'Item': {'pk': {'S': 'EXECUTION#exec-1'}}},
            ]
            # First update succeeds; cleanup update raises.
            mock_ddb.update_item.side_effect = [None, Exception('boom')]
            response = handler(event, None)

        # Primary operation (status update) must still be reported as 200.
        self.assertEqual(response['statusCode'], 200)

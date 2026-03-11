"""Unit tests for execute_test_suite Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from execute_test_suite import handler, resolve_triggered_by


@pytest.fixture
def mock_event():
    """Create a mock API Gateway event"""
    return {
        'body': json.dumps({
            'trigger_type': 'OnDemand'
        }),
        'pathParameters': {
            'suite_id': 'suite-123'
        },
        'requestContext': {
            'authorizer': {
                'email': 'test@example.com',
                'sub': 'user-123',
                'scope': 'api/suite.write api/admin'
            }
        }
    }


@pytest.fixture
def mock_suite():
    """Create a mock test suite"""
    return {
        'id': {'S': 'suite-123'},
        'name': {'S': 'Test Suite'},
        'scope': {'S': 'suite:test-suite'},
        'total_usecases': {'N': '2'}
    }


@pytest.fixture
def mock_usecases():
    """Create mock use case mappings"""
    return [
        {
            'usecase_id': {'S': 'usecase-1'},
            'usecase_name': {'S': 'Use Case 1'},
            'usecase_scope': {'S': 'usecase:test-1'}
        },
        {
            'usecase_id': {'S': 'usecase-2'},
            'usecase_name': {'S': 'Use Case 2'},
            'usecase_scope': {'S': 'usecase:test-2'}
        }
    ]


class TestExecuteTestSuite:
    """Test suite for execute_test_suite handler"""
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_execute_suite_success(self, mock_env_get, mock_dynamodb, mock_lambda, mock_event, mock_suite, mock_usecases):
        """Test successfully executing a test suite"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
        }.get(key, default)
        
        # Mock scope validation (admin scope bypasses)
        
        
        # Mock suite retrieval
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        
        # Mock use cases query
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        
        # Mock put_item and update_item
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}
        
        # Mock Lambda invocations
        mock_lambda.invoke.return_value = {'StatusCode': 202}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'suite_execution_id' in body
        assert body['suite_id'] == 'suite-123'
        assert body['suite_name'] == 'Test Suite'
        assert body['status'] == 'running'
        assert body['total_usecases'] == 2
        assert body['trigger_type'] == 'OnDemand'
        assert len(body['invocation_results']) == 2
        
        # Verify suite execution record was created
        assert mock_dynamodb.put_item.call_count >= 3  # 1 suite execution + 2 execution results
        
        # Verify Lambda invocations
        assert mock_lambda.invoke.call_count == 2
        
        # Verify invocation parameters
        for call in mock_lambda.invoke.call_args_list:
            kwargs = call[1]
            assert kwargs['FunctionName'] == 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
            assert kwargs['InvocationType'] == 'Event'
            payload = json.loads(kwargs['Payload'])
            assert payload['queryStringParameters']['trigger-type'] == 'OnDemandHeadless'
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_execute_suite_scheduled_trigger(self, mock_env_get, mock_dynamodb, mock_lambda, mock_suite, mock_usecases):
        """Test executing a suite with scheduled trigger type"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
        }.get(key, default)
        
        # Mock scope validation
        
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        mock_dynamodb.put_item.return_value = {}
        mock_lambda.invoke.return_value = {'StatusCode': 202}
        
        # Create event with scheduled trigger
        event = {
            'body': json.dumps({'trigger_type': 'ci_runner'}),
            'pathParameters': {'suite_id': 'suite-123'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['trigger_type'] == 'ci_runner'
    
    @patch('execute_test_suite.dynamodb')
    def test_suite_not_found(self, mock_dynamodb, mock_event):
        """Test error when suite doesn't exist"""
        # Mock suite retrieval (not found)
        mock_dynamodb.get_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error'] == 'Test suite not found'
    
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_suite_with_no_usecases(self, mock_env_get, mock_dynamodb, mock_event, mock_suite):
        """Test error when suite has no use cases"""
        # Setup mocks
        mock_env_get.return_value = 'test-table'
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        
        # Mock empty use cases query
        mock_dynamodb.query.return_value = {'Items': []}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Test suite has no use cases'
    
    def test_missing_suite_id(self):
        """Test error when suite_id is missing"""
        event = {
            'body': json.dumps({'trigger_type': 'OnDemand'}),
            'pathParameters': {},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'suite ID is required'
    
    def test_invalid_json_body(self):
        """Test error when request body is invalid JSON"""
        event = {
            'body': 'invalid json',
            'pathParameters': {'suite_id': 'suite-123'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Invalid JSON in request body'
    
    def test_invalid_trigger_type(self):
        """Test error when trigger_type is invalid"""
        event = {
            'body': json.dumps({'trigger_type': 'invalid'}),
            'pathParameters': {'suite_id': 'suite-123'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid trigger type' in body['error']
    
    def test_insufficient_scope(self):
        """Test error when user lacks required scope"""
        event = {
            'body': json.dumps({'trigger_type': 'OnDemand'}),
            'pathParameters': {'suite_id': 'suite-123'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/usecases.read'  # Wrong scope
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'Forbidden' in body['error']
    
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_suite_scope_validation(self, mock_env_get, mock_dynamodb, mock_event, mock_suite):
        """Test removed - no longer using per-suite scope validation"""
        pass
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_missing_lambda_arn_env_var(self, mock_env_get, mock_dynamodb, mock_lambda, mock_event, mock_suite, mock_usecases):
        """Test error when EXECUTE_USECASE_LAMBDA_ARN is not set"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': None
        }.get(key, default)
        
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'EXECUTE_USECASE_LAMBDA_ARN' in body['error']
        
        # Verify suite execution was updated to failed
        update_calls = [call for call in mock_dynamodb.update_item.call_args_list]
        assert len(update_calls) > 0
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_partial_invocation_failure(self, mock_env_get, mock_dynamodb, mock_lambda, mock_event, mock_suite, mock_usecases):
        """Test when some Lambda invocations fail"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
        }.get(key, default)
        
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}
        
        # Mock Lambda invocations: first succeeds, second fails
        mock_lambda.invoke.side_effect = [
            {'StatusCode': 202},
            Exception('Lambda invocation failed')
        ]
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify - should still succeed if at least one invocation worked
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['invocation_results']) == 2
        assert body['invocation_results'][0]['status'] == 'invoked'
        assert body['invocation_results'][1]['status'] == 'failed'
        
        # Verify failed execution result was updated
        update_calls = [call for call in mock_dynamodb.update_item.call_args_list]
        assert len(update_calls) > 0
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_all_invocations_fail(self, mock_env_get, mock_dynamodb, mock_lambda, mock_event, mock_suite, mock_usecases):
        """Test when all Lambda invocations fail"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
        }.get(key, default)
        
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}
        
        # Mock all Lambda invocations to fail
        mock_lambda.invoke.side_effect = Exception('Lambda invocation failed')
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Failed to invoke any use case executions' in body['error']
        assert len(body['invocation_results']) == 2
        assert all(r['status'] == 'failed' for r in body['invocation_results'])
        
        # Verify suite execution was updated to failed
        update_calls = [call for call in mock_dynamodb.update_item.call_args_list]
        assert len(update_calls) > 0
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_empty_body_defaults_to_manual(self, mock_env_get, mock_dynamodb, mock_lambda, mock_suite, mock_usecases):
        """Test that empty body defaults trigger_type to OnDemand"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
        }.get(key, default)
        
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        mock_dynamodb.put_item.return_value = {}
        mock_lambda.invoke.return_value = {'StatusCode': 202}
        
        # Create event with empty body
        event = {
            'body': '{}',
            'pathParameters': {'suite_id': 'suite-123'},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['trigger_type'] == 'OnDemand'
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_execution_result_records_created(self, mock_env_get, mock_dynamodb, mock_lambda, mock_event, mock_suite, mock_usecases):
        """Test that execution result records are created for each use case"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
        }.get(key, default)
        
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        mock_dynamodb.put_item.return_value = {}
        mock_lambda.invoke.return_value = {'StatusCode': 202}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        
        # Verify put_item was called for:
        # 1. Suite execution record
        # 2. Execution result for usecase-1
        # 3. Execution result for usecase-2
        assert mock_dynamodb.put_item.call_count == 3
        
        # Verify execution result records have correct structure
        put_calls = mock_dynamodb.put_item.call_args_list
        result_calls = [call for call in put_calls if 'SUITE_EXEC#' in str(call)]
        assert len(result_calls) == 2
    
    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    
    def test_user_context_passed_to_lambda(self, mock_env_get, mock_dynamodb, mock_lambda, mock_event, mock_suite, mock_usecases):
        """Test that user context is properly passed to execute_usecase Lambda"""
        # Setup mocks
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:execute-usecase'
        }.get(key, default)
        
        
        mock_dynamodb.get_item.return_value = {'Item': mock_suite}
        mock_dynamodb.query.return_value = {'Items': mock_usecases}
        mock_dynamodb.put_item.return_value = {}
        mock_lambda.invoke.return_value = {'StatusCode': 202}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        
        # Verify Lambda invocation payload includes user context
        invoke_call = mock_lambda.invoke.call_args_list[0]
        payload = json.loads(invoke_call[1]['Payload'])
        
        assert 'requestContext' in payload
        assert 'authorizer' in payload['requestContext']
        assert payload['requestContext']['authorizer']['email'] == 'test@example.com'
        assert payload['requestContext']['authorizer']['sub'] == 'user-123'
        assert 'api/suite.write' in payload['requestContext']['authorizer']['scope']



class TestResolveTriggeredBy:
    """Tests for resolve_triggered_by - resolves client_id to client_name for M2M tokens"""

    @patch('execute_test_suite.dynamodb')
    def test_user_identity_returns_email(self, mock_dynamodb):
        """User tokens return email directly without DynamoDB lookup"""
        identity = {'identity': 'user@example.com', 'identity_type': 'user'}
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'user@example.com'
        mock_dynamodb.get_item.assert_not_called()

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_resolves_to_name(self, mock_dynamodb):
        """M2M tokens look up client_name from OAUTH_CLIENTS record"""
        mock_dynamodb.get_item.return_value = {
            'Item': {'client_name': {'S': 'my-ci-runner'}}
        }
        identity = {'identity': 'abc123clientid', 'identity_type': 'client'}
        result = resolve_triggered_by(identity, 'test-table')

        assert result == 'my-ci-runner'
        mock_dynamodb.get_item.assert_called_once_with(
            TableName='test-table',
            Key={'pk': {'S': 'OAUTH_CLIENTS'}, 'sk': {'S': 'abc123clientid'}},
            ProjectionExpression='client_name'
        )

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_falls_back_to_id_when_not_found(self, mock_dynamodb):
        """Falls back to client_id when no OAUTH_CLIENTS record exists"""
        mock_dynamodb.get_item.return_value = {}
        identity = {'identity': 'abc123clientid', 'identity_type': 'client'}
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'abc123clientid'

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_falls_back_to_id_on_dynamo_error(self, mock_dynamodb):
        """Falls back to client_id when DynamoDB lookup fails"""
        mock_dynamodb.get_item.side_effect = Exception('DynamoDB timeout')
        identity = {'identity': 'abc123clientid', 'identity_type': 'client'}
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'abc123clientid'

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_falls_back_when_name_missing(self, mock_dynamodb):
        """Falls back to client_id when record exists but client_name attribute is missing"""
        mock_dynamodb.get_item.return_value = {
            'Item': {'pk': {'S': 'OAUTH_CLIENTS'}, 'sk': {'S': 'abc123clientid'}}
        }
        identity = {'identity': 'abc123clientid', 'identity_type': 'client'}
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'abc123clientid'



if __name__ == '__main__':
    pytest.main([__file__, '-v'])

import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock, call
from botocore.exceptions import ClientError
from update_suite_schedule import handler, validate_cron_expression, manage_eventbridge_rule


class TestValidateCronExpression(unittest.TestCase):
    """Test cron expression validation"""
    
    def test_valid_cron_expressions(self):
        """Test valid cron expressions"""
        valid_expressions = [
            '0 2 * * *',      # Daily at 2 AM
            '*/15 * * * *',   # Every 15 minutes
            '0 0 * * 0',      # Weekly on Sunday
            '0 9-17 * * 1-5', # Weekdays 9 AM to 5 PM
            '30 2 1 * *',     # First day of month at 2:30 AM
            '0 0,12 * * *',   # Twice daily at midnight and noon
        ]
        
        for expr in valid_expressions:
            with self.subTest(expr=expr):
                self.assertTrue(validate_cron_expression(expr))
    
    def test_invalid_cron_expressions(self):
        """Test invalid cron expressions"""
        invalid_expressions = [
            '',                    # Empty
            '0 2 * *',            # Too few parts
            '0 2 * * * *',        # Too many parts
            '0 2 * * * * *',      # Way too many parts
            'invalid',            # Not a cron expression
            '0 2 * * MON',        # Named day (not supported in basic validation)
            '0 2 * JAN *',        # Named month (not supported in basic validation)
            None,                 # None
            123,                  # Not a string
        ]
        
        for expr in invalid_expressions:
            with self.subTest(expr=expr):
                self.assertFalse(validate_cron_expression(expr))


class TestUpdateSuiteSchedule(unittest.TestCase):
    """Test suite for update_suite_schedule Lambda function"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['BASE_NAME'] = 'test-app'
        os.environ['EXECUTE_SUITE_LAMBDA_ARN'] = 'arn:aws:lambda:us-east-1:123456789012:function:execute-suite'
        
        # Mock existing suite
        self.existing_suite = {
            'pk': 'TEST_SUITES',
            'sk': 'SUITE#suite-123',
            'id': 'suite-123',
            'name': 'Test Suite',
            'description': 'Test description',
            'scope': 'suite:smoke-tests',
            'tags': ['smoke'],
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
            'created_by': 'user-123',
            'total_usecases': 5,
            'schedule_enabled': False
        }
    
    def test_enable_schedule_success(self):
        """Test successfully enabling a schedule"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'schedule_enabled': True,
                'schedule_expression': '0 2 * * *',
                'schedule_timezone': 'UTC'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            # Mock DynamoDB
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['schedule_enabled'] = True
            updated_suite['schedule_expression'] = '0 2 * * *'
            updated_suite['schedule_timezone'] = 'UTC'
            updated_suite['updated_at'] = '2024-01-02T00:00:00Z'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            # Mock Amazon EventBridge
            mock_events = MagicMock()
            mock_boto3.client.return_value = mock_events
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['schedule_enabled'], True)
            self.assertEqual(body['schedule_expression'], '0 2 * * *')
            self.assertEqual(body['schedule_timezone'], 'UTC')
            
            # Verify Amazon EventBridge rule was created
            mock_events.put_rule.assert_called_once()
            mock_events.put_targets.assert_called_once()
    
    def test_disable_schedule_success(self):
        """Test successfully disabling a schedule"""
        # Suite with schedule enabled
        suite_with_schedule = self.existing_suite.copy()
        suite_with_schedule['schedule_enabled'] = True
        suite_with_schedule['schedule_expression'] = '0 2 * * *'
        suite_with_schedule['schedule_timezone'] = 'UTC'
        
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'schedule_enabled': False
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            # Mock DynamoDB
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': suite_with_schedule}
            
            updated_suite = suite_with_schedule.copy()
            updated_suite['schedule_enabled'] = False
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            # Mock Amazon EventBridge
            mock_events = MagicMock()
            mock_boto3.client.return_value = mock_events
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['schedule_enabled'], False)
            
            # Verify Amazon EventBridge rule was disabled
            mock_events.disable_rule.assert_called_once_with(Name='test-app-suite-suite-123')
    
    def test_update_schedule_expression_only(self):
        """Test updating only the schedule expression"""
        suite_with_schedule = self.existing_suite.copy()
        suite_with_schedule['schedule_enabled'] = True
        suite_with_schedule['schedule_expression'] = '0 2 * * *'
        
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'schedule_expression': '0 3 * * *'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': suite_with_schedule}
            
            updated_suite = suite_with_schedule.copy()
            updated_suite['schedule_expression'] = '0 3 * * *'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            mock_events = MagicMock()
            mock_boto3.client.return_value = mock_events
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['schedule_expression'], '0 3 * * *')
    
    def test_invalid_cron_expression(self):
        """Test that invalid cron expression returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'schedule_expression': 'invalid cron'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('Invalid cron expression', body['error'])
    
    def test_missing_suite_id(self):
        """Test that missing suite_id returns 400"""
        event = {
            'pathParameters': {},
            'body': json.dumps({'schedule_enabled': True}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('suite ID is required', body['error'])
    
    def test_suite_not_found(self):
        """Test that non-existent suite returns 404"""
        event = {
            'pathParameters': {'suite_id': 'nonexistent'},
            'body': json.dumps({'schedule_enabled': True}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 404)
            body = json.loads(response['body'])
            self.assertIn('not found', body['error'])
    
    def test_no_fields_to_update(self):
        """Test that empty update body returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('At least one schedule field', body['error'])
    
    def test_invalid_schedule_enabled_type(self):
        """Test that non-boolean schedule_enabled returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'schedule_enabled': 'yes'}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('schedule_enabled must be a boolean', body['error'])
    
    def test_empty_schedule_expression(self):
        """Test that empty schedule_expression returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'schedule_expression': '   '}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('schedule_expression cannot be empty', body['error'])
    
    def test_empty_schedule_timezone(self):
        """Test that empty schedule_timezone returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'schedule_timezone': '   '}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('schedule_timezone cannot be empty', body['error'])
    
    def test_insufficient_api_scope(self):
        """Test that missing api/suite.write scope returns 403"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'schedule_enabled': True}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/usecases.read'
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
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'schedule_enabled': False}),
            'requestContext': {
                'authorizer': {
                    'email': 'admin@example.com',
                    'sub': 'admin-123',
                    'scope': 'api/admin'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['schedule_enabled'] = False
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            mock_events = MagicMock()
            mock_boto3.client.return_value = mock_events
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
    
    def test_eventbridge_error_handling(self):
        """Test that Amazon EventBridge errors are handled properly"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'schedule_enabled': True,
                'schedule_expression': '0 2 * * *'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['schedule_enabled'] = True
            updated_suite['schedule_expression'] = '0 2 * * *'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            # Mock Amazon EventBridge to raise error
            mock_events = MagicMock()
            mock_events.put_rule.side_effect = ClientError(
                {'Error': {'Code': 'InternalError', 'Message': 'Service error'}},
                'PutRule'
            )
            mock_boto3.client.return_value = mock_events
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 500)
            body = json.loads(response['body'])
            self.assertIn('Failed to update Amazon EventBridge rule', body['error'])
    
    def test_disable_nonexistent_rule(self):
        """Test disabling a rule that doesn't exist (should succeed)"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'schedule_enabled': False}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_suite_schedule.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['schedule_enabled'] = False
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            # Mock Amazon EventBridge to raise ResourceNotFoundException
            mock_events = MagicMock()
            mock_events.disable_rule.side_effect = ClientError(
                {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Rule not found'}},
                'DisableRule'
            )
            mock_boto3.client.return_value = mock_events
            
            response = handler(event, None)
            
            # Should succeed even if rule doesn't exist
            self.assertEqual(response['statusCode'], 200)
    
    def test_invalid_json(self):
        """Test that invalid JSON returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': 'not valid json',
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid JSON', body['error'])


class TestManageEventBridgeRule(unittest.TestCase):
    """Test Amazon EventBridge rule management function"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['BASE_NAME'] = 'test-app'
        os.environ['EXECUTE_SUITE_LAMBDA_ARN'] = 'arn:aws:lambda:us-east-1:123456789012:function:execute-suite'
    
    @patch('update_suite_schedule.boto3.client')
    def test_enable_rule_creates_rule_and_target(self, mock_boto_client):
        """Test enabling a rule creates Amazon EventBridge rule and target"""
        mock_events = MagicMock()
        mock_boto_client.return_value = mock_events
        
        manage_eventbridge_rule(
            suite_id='suite-123',
            schedule_enabled=True,
            schedule_expression='0 2 * * *',
            schedule_timezone='UTC'
        )
        
        # Verify rule was created
        mock_events.put_rule.assert_called_once()
        call_args = mock_events.put_rule.call_args
        self.assertEqual(call_args[1]['Name'], 'test-app-suite-suite-123')
        self.assertEqual(call_args[1]['ScheduleExpression'], 'cron(0 2 * * * *)')
        self.assertEqual(call_args[1]['State'], 'ENABLED')
        
        # Verify target was added
        mock_events.put_targets.assert_called_once()
        target_call_args = mock_events.put_targets.call_args
        self.assertEqual(target_call_args[1]['Rule'], 'test-app-suite-suite-123')
        targets = target_call_args[1]['Targets']
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]['Arn'], 'arn:aws:lambda:us-east-1:123456789012:function:execute-suite')
    
    @patch('update_suite_schedule.boto3.client')
    def test_disable_rule_disables_eventbridge_rule(self, mock_boto_client):
        """Test disabling a rule calls disable_rule"""
        mock_events = MagicMock()
        mock_boto_client.return_value = mock_events
        
        manage_eventbridge_rule(
            suite_id='suite-123',
            schedule_enabled=False
        )
        
        # Verify rule was disabled
        mock_events.disable_rule.assert_called_once_with(Name='test-app-suite-suite-123')
        
        # Verify rule was not created
        mock_events.put_rule.assert_not_called()
        mock_events.put_targets.assert_not_called()
    
    @patch('update_suite_schedule.boto3.client')
    def test_enable_without_expression_raises_error(self, mock_boto_client):
        """Test enabling without schedule_expression raises ValueError"""
        mock_events = MagicMock()
        mock_boto_client.return_value = mock_events
        
        with self.assertRaises(ValueError) as context:
            manage_eventbridge_rule(
                suite_id='suite-123',
                schedule_enabled=True,
                schedule_expression=None
            )
        
        self.assertIn('schedule_expression is required', str(context.exception))
    
    @patch('update_suite_schedule.boto3.client')
    def test_missing_lambda_arn_raises_error(self, mock_boto_client):
        """Test missing EXECUTE_SUITE_LAMBDA_ARN raises ValueError"""
        del os.environ['EXECUTE_SUITE_LAMBDA_ARN']
        
        mock_events = MagicMock()
        mock_boto_client.return_value = mock_events
        
        with self.assertRaises(ValueError) as context:
            manage_eventbridge_rule(
                suite_id='suite-123',
                schedule_enabled=True,
                schedule_expression='0 2 * * *'
            )
        
        self.assertIn('EXECUTE_SUITE_LAMBDA_ARN', str(context.exception))
        
        # Restore for other tests
        os.environ['EXECUTE_SUITE_LAMBDA_ARN'] = 'arn:aws:lambda:us-east-1:123456789012:function:execute-suite'


if __name__ == '__main__':
    unittest.main()

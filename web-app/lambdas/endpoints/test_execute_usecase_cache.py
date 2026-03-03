"""Unit tests for cache field copying in execute_usecase.py"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from execute_usecase import handler


class TestExecuteUsecaseCacheFields:
    """Test suite for cache field copying in execute_usecase"""
    
    @patch('execute_usecase.eventbridge')
    @patch('execute_usecase.ecs')
    @patch('execute_usecase.sqs')
    @patch('execute_usecase.dynamodb')
    @patch('execute_usecase.allow_m2m_token')
    def test_cache_fields_copied_to_execution_steps(
        self, mock_allow_m2m, mock_dynamodb, mock_sqs, mock_ecs, mock_eventbridge
    ):
        """Test that cache fields are copied from STEP to EXECUTION_STEP"""
        mock_allow_m2m.return_value = ({'identity': 'test@example.com', 'identity_type': 'user'}, None)
        
        # Mock usecase
        mock_dynamodb.get_item.side_effect = [
            {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'nova-act-v1'}
                }
            }
        ]
        
        # Mock steps with cache fields
        mock_dynamodb.query.return_value = {
            'Items': [
                {
                    'id': {'S': 'step1'},
                    'sort': {'N': '0'},
                    'instruction': {'S': 'Click login'},
                    'step_type': {'S': 'navigation'},
                    'cached_steps': {'S': '[{"type":"click","bbox":{"x1":100,"y1":200,"x2":300,"y2":400}}]'},
                    'cache_last_updated': {'S': '2026-03-03T10:00:00Z'}
                },
                {
                    'id': {'S': 'step2'},
                    'sort': {'N': '1'},
                    'instruction': {'S': 'Verify title'},
                    'step_type': {'S': 'validation'}
                }
            ]
        }
        
        # Mock SQS
        mock_sqs.send_message.return_value = {'MessageId': 'msg123'}
        
        event = {
            'pathParameters': {'id': 'usecase123'},
            'queryStringParameters': None,
            'requestContext': {'authorizer': {'claims': {}}}
        }
        
        with patch('execute_usecase.get_table_name', return_value='test-table'):
            with patch('execute_usecase.get_current_timestamp', return_value='2026-03-03T12:00:00Z'):
                with patch('execute_usecase.generate_uuid7', side_effect=['exec123', 'execstep1', 'execstep2']):
                    response = handler(event, None)
        
        assert response['statusCode'] == 200
        
        # Verify put_item calls for execution steps
        put_item_calls = [call for call in mock_dynamodb.put_item.call_args_list]
        
        # Find execution step items
        execution_steps = [
            call[1]['Item'] for call in put_item_calls 
            if call[1]['Item']['pk']['S'].startswith('EXECUTION#')
            and call[1]['Item']['sk']['S'].startswith('EXECUTION_STEP#')
        ]
        
        assert len(execution_steps) == 2
        
        # First step should have cache fields
        step1 = execution_steps[0]
        assert 'cached_steps' in step1
        assert step1['cached_steps']['S'] == '[{"type":"click","bbox":{"x1":100,"y1":200,"x2":300,"y2":400}}]'
        assert 'cache_last_updated' in step1
        assert step1['cache_last_updated']['S'] == '2026-03-03T10:00:00Z'
        
        # Second step should not have cache fields
        step2 = execution_steps[1]
        assert 'cached_steps' not in step2
        assert 'cache_last_updated' not in step2
    
    @patch('execute_usecase.eventbridge')
    @patch('execute_usecase.ecs')
    @patch('execute_usecase.sqs')
    @patch('execute_usecase.dynamodb')
    @patch('execute_usecase.allow_m2m_token')
    def test_execution_works_without_cache_fields(
        self, mock_allow_m2m, mock_dynamodb, mock_sqs, mock_ecs, mock_eventbridge
    ):
        """Test that execution works normally when no cache fields present"""
        mock_allow_m2m.return_value = ({'identity': 'test@example.com', 'identity_type': 'user'}, None)
        
        # Mock usecase
        mock_dynamodb.get_item.side_effect = [
            {
                'Item': {
                    'starting_url': {'S': 'https://example.com'},
                    'executing_region': {'S': 'us-east-1'},
                    'model_id': {'S': 'nova-act-v1'}
                }
            }
        ]
        
        # Mock steps without cache fields
        mock_dynamodb.query.return_value = {
            'Items': [
                {
                    'id': {'S': 'step1'},
                    'sort': {'N': '0'},
                    'instruction': {'S': 'Click login'},
                    'step_type': {'S': 'navigation'}
                }
            ]
        }
        
        # Mock SQS
        mock_sqs.send_message.return_value = {'MessageId': 'msg123'}
        
        event = {
            'pathParameters': {'id': 'usecase123'},
            'queryStringParameters': None,
            'requestContext': {'authorizer': {'claims': {}}}
        }
        
        with patch('execute_usecase.get_table_name', return_value='test-table'):
            with patch('execute_usecase.get_current_timestamp', return_value='2026-03-03T12:00:00Z'):
                with patch('execute_usecase.generate_uuid7', side_effect=['exec123', 'execstep1']):
                    response = handler(event, None)
        
        assert response['statusCode'] == 200
        
        # Verify execution step created without cache fields
        put_item_calls = [call for call in mock_dynamodb.put_item.call_args_list]
        execution_steps = [
            call[1]['Item'] for call in put_item_calls 
            if call[1]['Item']['pk']['S'].startswith('EXECUTION#')
            and call[1]['Item']['sk']['S'].startswith('EXECUTION_STEP#')
        ]
        
        assert len(execution_steps) == 1
        step = execution_steps[0]
        assert 'cached_steps' not in step
        assert 'cache_last_updated' not in step

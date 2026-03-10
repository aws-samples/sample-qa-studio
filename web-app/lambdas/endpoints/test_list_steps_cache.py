"""Unit tests for cache field support in list_steps.py"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from list_steps import handler


class TestListStepsCacheFields:
    """Test suite for cache field support in list_steps"""
    
    @patch('list_steps.boto3.resource')
    @patch('list_steps.require_scopes')
    def test_list_steps_with_cache_fields(self, mock_require_scopes, mock_boto3_resource):
        """Test that cache fields are returned when present"""
        mock_require_scopes.return_value = ({'identity': 'test@example.com'}, None)
        
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'USECASE#123',
                    'sk': 'STEP#step1',
                    'id': 'step1',
                    'sort': 0,
                    'instruction': 'Click login',
                    'step_type': 'navigation',
                    'cached_steps': '[{"type":"click","bbox":{"x1":100,"y1":200,"x2":300,"y2":400}}]',
                    'cache_last_updated': '2026-03-03T10:00:00Z'
                }
            ]
        }
        
        event = {
            'pathParameters': {'id': '123'},
            'requestContext': {'authorizer': {'claims': {'cognito:groups': '["api/usecases.read"]'}}}
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['steps']) == 1
        assert body['steps'][0]['cached_steps'] == '[{"type":"click","bbox":{"x1":100,"y1":200,"x2":300,"y2":400}}]'
        assert body['steps'][0]['cache_last_updated'] == '2026-03-03T10:00:00Z'
    
    @patch('list_steps.boto3.resource')
    @patch('list_steps.require_scopes')
    def test_list_steps_without_cache_fields(self, mock_require_scopes, mock_boto3_resource):
        """Test that cache fields return None when not present"""
        mock_require_scopes.return_value = ({'identity': 'test@example.com'}, None)
        
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'USECASE#123',
                    'sk': 'STEP#step1',
                    'id': 'step1',
                    'sort': 0,
                    'instruction': 'Click login',
                    'step_type': 'navigation'
                }
            ]
        }
        
        event = {
            'pathParameters': {'id': '123'},
            'requestContext': {'authorizer': {'claims': {'cognito:groups': '["api/usecases.read"]'}}}
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['steps']) == 1
        assert body['steps'][0]['cached_steps'] is None
        assert body['steps'][0]['cache_last_updated'] is None
    
    @patch('list_steps.boto3.resource')
    @patch('list_steps.require_scopes')
    def test_list_steps_mixed_cache_fields(self, mock_require_scopes, mock_boto3_resource):
        """Test that some steps with cache and some without work correctly"""
        mock_require_scopes.return_value = ({'identity': 'test@example.com'}, None)
        
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'USECASE#123',
                    'sk': 'STEP#step1',
                    'id': 'step1',
                    'sort': 0,
                    'instruction': 'Click login',
                    'step_type': 'navigation',
                    'cached_steps': '[{"type":"click"}]',
                    'cache_last_updated': '2026-03-03T10:00:00Z'
                },
                {
                    'pk': 'USECASE#123',
                    'sk': 'STEP#step2',
                    'id': 'step2',
                    'sort': 1,
                    'instruction': 'Verify title',
                    'step_type': 'validation'
                }
            ]
        }
        
        event = {
            'pathParameters': {'id': '123'},
            'requestContext': {'authorizer': {'claims': {'cognito:groups': '["api/usecases.read"]'}}}
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['steps']) == 2
        assert body['steps'][0]['cached_steps'] == '[{"type":"click"}]'
        assert body['steps'][0]['cache_last_updated'] == '2026-03-03T10:00:00Z'
        assert body['steps'][1]['cached_steps'] is None
        assert body['steps'][1]['cache_last_updated'] is None

"""
Unit tests for enable_cache field in usecase endpoints.
Tests create_usecase, get_usecase, and update_usecase handlers.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from moto import mock_aws
import boto3
import os

# Set environment variables before importing handlers
os.environ['TABLE_NAME'] = 'test-table'
os.environ['DEFAULT_REGION'] = 'us-east-1'

from create_usecase import handler as create_handler
from get_usecase import handler as get_handler
from update_usecase import handler as update_handler


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-table',
            KeySchema=[
                {'AttributeName': 'pk', 'KeyType': 'HASH'},
                {'AttributeName': 'sk', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'pk', 'AttributeType': 'S'},
                {'AttributeName': 'sk', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        yield table


@pytest.fixture
def mock_user_identity():
    """Mock user identity for authorization."""
    return {
        'email': 'test@example.com',
        'sub': 'test-sub-123',
        'scopes': ['api/usecases.write', 'api/usecases.read']
    }


def test_create_usecase_with_enable_cache_true(dynamodb_table, mock_user_identity):
    """Test creating a usecase with enableCache=True."""
    with patch('create_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'body': json.dumps({
                'name': 'Test Usecase',
                'description': 'Test description',
                'starting_url': 'https://example.com',
                'enableCache': True
            })
        }
        
        response = create_handler(event, None)
        
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['enable_cache'] is True


def test_create_usecase_with_enable_cache_false(dynamodb_table, mock_user_identity):
    """Test creating a usecase with enableCache=False."""
    with patch('create_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'body': json.dumps({
                'name': 'Test Usecase',
                'description': 'Test description',
                'starting_url': 'https://example.com',
                'enableCache': False
            })
        }
        
        response = create_handler(event, None)
        
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['enable_cache'] is False


def test_create_usecase_default_enable_cache(dynamodb_table, mock_user_identity):
    """Test creating a usecase without enableCache field defaults to False."""
    with patch('create_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'body': json.dumps({
                'name': 'Test Usecase',
                'description': 'Test description',
                'starting_url': 'https://example.com'
            })
        }
        
        response = create_handler(event, None)
        
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['enable_cache'] is False


def test_get_usecase_returns_enable_cache_as_camelcase(dynamodb_table, mock_user_identity):
    """Test that get_usecase transforms enable_cache to enableCache."""
    # First create a usecase
    dynamodb_table.put_item(Item={
        'pk': 'USECASES',
        'sk': 'USECASE#test-id',
        'id': 'test-id',
        'name': 'Test Usecase',
        'enable_cache': True
    })
    
    with patch('get_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'pathParameters': {'id': 'test-id'}
        }
        
        response = get_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['enableCache'] is True
        assert body['enable_cache'] is True  # Original field still present


def test_get_usecase_default_enable_cache_false(dynamodb_table, mock_user_identity):
    """Test that get_usecase returns enableCache=False for usecases without the field."""
    # Create a usecase without enable_cache field
    dynamodb_table.put_item(Item={
        'pk': 'USECASES',
        'sk': 'USECASE#test-id',
        'id': 'test-id',
        'name': 'Test Usecase'
    })
    
    with patch('get_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'pathParameters': {'id': 'test-id'}
        }
        
        response = get_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['enableCache'] is False


def test_update_usecase_enable_cache_true(dynamodb_table, mock_user_identity):
    """Test updating a usecase to enable cache."""
    # Create initial usecase
    dynamodb_table.put_item(Item={
        'pk': 'USECASES',
        'sk': 'USECASE#test-id',
        'id': 'test-id',
        'name': 'Test Usecase',
        'description': 'Test',
        'starting_url': 'https://example.com',
        'active': False,
        'executing_region': 'us-east-1',
        'enable_cache': False
    })
    
    with patch('update_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'pathParameters': {'id': 'test-id'},
            'body': json.dumps({
                'name': 'Test Usecase',
                'description': 'Test',
                'starting_url': 'https://example.com',
                'active': False,
                'enableCache': True
            })
        }
        
        response = update_handler(event, None)
        
        assert response['statusCode'] == 200
        
        # Verify the update
        item = dynamodb_table.get_item(Key={'pk': 'USECASES', 'sk': 'USECASE#test-id'})['Item']
        assert item['enable_cache'] is True


def test_update_usecase_enable_cache_false(dynamodb_table, mock_user_identity):
    """Test updating a usecase to disable cache."""
    # Create initial usecase with cache enabled
    dynamodb_table.put_item(Item={
        'pk': 'USECASES',
        'sk': 'USECASE#test-id',
        'id': 'test-id',
        'name': 'Test Usecase',
        'description': 'Test',
        'starting_url': 'https://example.com',
        'active': False,
        'executing_region': 'us-east-1',
        'enable_cache': True
    })
    
    with patch('update_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'pathParameters': {'id': 'test-id'},
            'body': json.dumps({
                'name': 'Test Usecase',
                'description': 'Test',
                'starting_url': 'https://example.com',
                'active': False,
                'enableCache': False
            })
        }
        
        response = update_handler(event, None)
        
        assert response['statusCode'] == 200
        
        # Verify the update
        item = dynamodb_table.get_item(Key={'pk': 'USECASES', 'sk': 'USECASE#test-id'})['Item']
        assert item['enable_cache'] is False


def test_update_usecase_without_enable_cache_field(dynamodb_table, mock_user_identity):
    """Test updating a usecase without providing enableCache field doesn't change it."""
    # Create initial usecase with cache enabled
    dynamodb_table.put_item(Item={
        'pk': 'USECASES',
        'sk': 'USECASE#test-id',
        'id': 'test-id',
        'name': 'Test Usecase',
        'description': 'Test',
        'starting_url': 'https://example.com',
        'active': False,
        'executing_region': 'us-east-1',
        'enable_cache': True
    })
    
    with patch('update_usecase.require_scopes', return_value=(mock_user_identity, None)):
        event = {
            'pathParameters': {'id': 'test-id'},
            'body': json.dumps({
                'name': 'Updated Name',
                'description': 'Test',
                'starting_url': 'https://example.com',
                'active': False
            })
        }
        
        response = update_handler(event, None)
        
        assert response['statusCode'] == 200
        
        # Verify enable_cache is unchanged
        item = dynamodb_table.get_item(Key={'pk': 'USECASES', 'sk': 'USECASE#test-id'})['Item']
        assert item['enable_cache'] is True
        assert item['name'] == 'Updated Name'

import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from update_test_suite import handler


class TestUpdateTestSuite(unittest.TestCase):
    """Test suite for update_test_suite Lambda function"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        
        # Mock existing suite
        self.existing_suite = {
            'pk': 'TEST_SUITES',
            'sk': 'SUITE#suite-123',
            'id': 'suite-123',
            'name': 'Original Name',
            'description': 'Original description',
            'scope': 'suite:smoke-tests',
            'tags': ['smoke'],
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
            'created_by': 'user-123',
            'total_usecases': 5,
            'schedule_enabled': False
        }
    
    def test_update_suite_name_success(self):
        """Test successful update of suite name"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'name': 'Updated Name'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            # Mock get_item to return existing suite
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            # Mock update_item to return updated suite
            updated_suite = self.existing_suite.copy()
            updated_suite['name'] = 'Updated Name'
            updated_suite['updated_at'] = '2024-01-02T00:00:00Z'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['name'], 'Updated Name')
            self.assertNotEqual(body['updated_at'], self.existing_suite['updated_at'])
            
            # Verify update_item was called
            mock_table.update_item.assert_called_once()
    
    def test_update_suite_description_success(self):
        """Test successful update of suite description"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'description': 'Updated description'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['description'] = 'Updated description'
            updated_suite['updated_at'] = '2024-01-02T00:00:00Z'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['description'], 'Updated description')
    
    def test_update_suite_tags_success(self):
        """Test successful update of suite tags"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'tags': ['smoke', 'critical', 'nightly']
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['tags'] = ['smoke', 'critical', 'nightly']
            updated_suite['updated_at'] = '2024-01-02T00:00:00Z'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['tags'], ['smoke', 'critical', 'nightly'])
    
    def test_update_multiple_fields_success(self):
        """Test successful update of multiple fields at once"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({
                'name': 'New Name',
                'description': 'New description',
                'tags': ['new', 'tags']
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['name'] = 'New Name'
            updated_suite['description'] = 'New description'
            updated_suite['tags'] = ['new', 'tags']
            updated_suite['updated_at'] = '2024-01-02T00:00:00Z'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['name'], 'New Name')
            self.assertEqual(body['description'], 'New description')
            self.assertEqual(body['tags'], ['new', 'tags'])
    
    def test_missing_suite_id(self):
        """Test that missing suite_id returns 400"""
        event = {
            'pathParameters': {},
            'body': json.dumps({'name': 'Updated Name'}),
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
            'body': json.dumps({'name': 'Updated Name'}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            # Mock get_item to return no item
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
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('At least one field', body['error'])
    
    def test_name_too_short(self):
        """Test that name shorter than 3 characters returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'name': 'AB'}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('between 3 and 100 characters', body['error'])
    
    def test_name_too_long(self):
        """Test that name longer than 100 characters returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'name': 'A' * 101}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('between 3 and 100 characters', body['error'])
    
    def test_empty_name(self):
        """Test that empty name returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'name': '   '}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('cannot be empty', body['error'])
    
    def test_description_too_long(self):
        """Test that description longer than 500 characters returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'description': 'A' * 501}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('500 characters or less', body['error'])
    
    def test_empty_description(self):
        """Test that empty description returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'description': '   '}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('cannot be empty', body['error'])
    
    def test_invalid_tags_type(self):
        """Test that non-array tags returns 400"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'tags': 'not-an-array'}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 400)
            body = json.loads(response['body'])
            self.assertIn('tags must be an array', body['error'])
    
    def test_insufficient_api_scope(self):
        """Test that missing api/suite.write scope returns 403"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'name': 'Updated Name'}),
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
    
    def test_insufficient_suite_scope(self):
        """Test removed - no longer using per-suite scope validation"""
        pass
    
    def test_admin_scope_grants_access(self):
        """Test that api/admin scope grants access"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'name': 'Updated Name'}),
            'requestContext': {
                'authorizer': {
                    'email': 'admin@example.com',
                    'sub': 'admin-123',
                    'scope': 'api/admin'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['name'] = 'Updated Name'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
    
    def test_wildcard_suite_scope_grants_access(self):
        """Test that suite:*:write scope grants access to any suite"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'body': json.dumps({'name': 'Updated Name'}),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('update_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            mock_table.get_item.return_value = {'Item': self.existing_suite}
            
            updated_suite = self.existing_suite.copy()
            updated_suite['name'] = 'Updated Name'
            mock_table.update_item.return_value = {'Attributes': updated_suite}
            
            response = handler(event, None)
            
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


if __name__ == '__main__':
    unittest.main()

"""Unit tests for list_test_suites.py Lambda function"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from list_test_suites import handler, has_scope_access


class TestHasScopeAccess:
    """Test suite for has_scope_access helper function"""
    
    def test_admin_scope_grants_access(self):
        """Test that admin scope grants access to all suites"""
        user_scopes = ['api/admin']
        assert has_scope_access(user_scopes, 'suite:smoke-tests') is True
    
    def test_wildcard_scope_grants_access(self):
        """Test that wildcard scope grants access"""
        user_scopes = ['suite:smoke-tests:*']
        assert has_scope_access(user_scopes, 'suite:smoke-tests') is True
    
    def test_read_permission_grants_access(self):
        """Test that read permission grants access"""
        user_scopes = ['suite:smoke-tests:read']
        assert has_scope_access(user_scopes, 'suite:smoke-tests') is True
    
    def test_write_permission_grants_access(self):
        """Test that write permission grants read access"""
        user_scopes = ['suite:smoke-tests:write']
        assert has_scope_access(user_scopes, 'suite:smoke-tests') is True
    
    def test_no_matching_scope_denies_access(self):
        """Test that missing scope denies access"""
        user_scopes = ['suite:other-suite:read']
        assert has_scope_access(user_scopes, 'suite:smoke-tests') is False
    
    def test_empty_scopes_denies_access(self):
        """Test that empty scopes denies access"""
        user_scopes = []
        assert has_scope_access(user_scopes, 'suite:smoke-tests') is False
    
    def test_execute_permission_does_not_grant_read_access(self):
        """Test that execute permission alone does not grant read access"""
        user_scopes = ['suite:smoke-tests:execute']
        assert has_scope_access(user_scopes, 'suite:smoke-tests') is False


class TestListTestSuitesHandler:
    """Test suite for list_test_suites handler function"""
    
    @patch('list_test_suites.boto3.resource')
    @patch('list_test_suites.require_scopes')
    def test_list_suites_success(self, mock_require_scopes, mock_boto3_resource):
        """Test successful listing of test suites"""
        # Mock user identity with scopes
        mock_require_scopes.return_value = (
            {
                'identity': 'test@example.com',
                'scopes': ['api/suite.read', 'suite:smoke-tests:read', 'suite:regression:read']
            },
            None
        )
        
        # Mock DynamoDB response
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#123',
                    'id': '123',
                    'name': 'Smoke Tests',
                    'description': 'Critical path tests',
                    'scope': 'suite:smoke-tests',
                    'tags': ['smoke', 'critical'],
                    'total_usecases': 5
                },
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#456',
                    'id': '456',
                    'name': 'Regression Tests',
                    'description': 'Full regression suite',
                    'scope': 'suite:regression',
                    'tags': ['regression'],
                    'total_usecases': 20
                },
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#789',
                    'id': '789',
                    'name': 'Integration Tests',
                    'description': 'Integration test suite',
                    'scope': 'suite:integration',
                    'tags': ['integration'],
                    'total_usecases': 10
                }
            ]
        }
        
        # Call handler
        event = {'queryStringParameters': None}
        response = handler(event, None)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'suites' in body
        
        # With simplified authorization, users with api/suite.read can see all suites
        assert len(body['suites']) == 3
        suite_names = [s['name'] for s in body['suites']]
        assert 'Smoke Tests' in suite_names
        assert 'Regression Tests' in suite_names
        assert 'Integration Tests' in suite_names
        
        # Verify pk/sk are removed from response
        for suite in body['suites']:
            assert 'pk' not in suite
            assert 'sk' not in suite
    
    @patch('list_test_suites.boto3.resource')
    @patch('list_test_suites.require_scopes')
    def test_list_suites_with_admin_scope(self, mock_require_scopes, mock_boto3_resource):
        """Test that admin scope grants access to all suites"""
        # Mock user identity with admin scope
        mock_require_scopes.return_value = (
            {
                'identity': 'admin@example.com',
                'scopes': ['api/admin']
            },
            None
        )
        
        # Mock DynamoDB response
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#123',
                    'id': '123',
                    'name': 'Suite 1',
                    'scope': 'suite:suite1',
                    'tags': []
                },
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#456',
                    'id': '456',
                    'name': 'Suite 2',
                    'scope': 'suite:suite2',
                    'tags': []
                }
            ]
        }
        
        # Call handler
        event = {'queryStringParameters': None}
        response = handler(event, None)
        
        # Verify response - admin should see all suites
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['suites']) == 2
    
    @patch('list_test_suites.boto3.resource')
    @patch('list_test_suites.require_scopes')
    def test_list_suites_filter_by_tag(self, mock_require_scopes, mock_boto3_resource):
        """Test filtering suites by tag"""
        # Mock user identity
        mock_require_scopes.return_value = (
            {
                'identity': 'test@example.com',
                'scopes': ['api/suite.read', 'suite:smoke-tests:read', 'suite:regression:read']
            },
            None
        )
        
        # Mock DynamoDB response
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#123',
                    'id': '123',
                    'name': 'Smoke Tests',
                    'scope': 'suite:smoke-tests',
                    'tags': ['smoke', 'critical']
                },
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#456',
                    'id': '456',
                    'name': 'Regression Tests',
                    'scope': 'suite:regression',
                    'tags': ['regression']
                }
            ]
        }
        
        # Call handler with tag filter
        event = {'queryStringParameters': {'tag': 'smoke'}}
        response = handler(event, None)
        
        # Verify response - should only return suites with 'smoke' tag
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['suites']) == 1
        assert body['suites'][0]['name'] == 'Smoke Tests'
    
    @patch('list_test_suites.boto3.resource')
    @patch('list_test_suites.require_scopes')
    def test_list_suites_filter_by_scope(self, mock_require_scopes, mock_boto3_resource):
        """Test filtering suites by scope"""
        # Mock user identity
        mock_require_scopes.return_value = (
            {
                'identity': 'test@example.com',
                'scopes': ['api/suite.read', 'suite:smoke-tests:read', 'suite:regression:read']
            },
            None
        )
        
        # Mock DynamoDB response
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#123',
                    'id': '123',
                    'name': 'Smoke Tests',
                    'scope': 'suite:smoke-tests',
                    'tags': []
                },
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#456',
                    'id': '456',
                    'name': 'Regression Tests',
                    'scope': 'suite:regression',
                    'tags': []
                }
            ]
        }
        
        # Call handler with scope filter
        event = {'queryStringParameters': {'scope': 'suite:smoke-tests'}}
        response = handler(event, None)
        
        # Verify response - should only return suites with matching scope
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['suites']) == 1
        assert body['suites'][0]['name'] == 'Smoke Tests'
    
    @patch('list_test_suites.boto3.resource')
    @patch('list_test_suites.require_scopes')
    def test_list_suites_filter_by_tag_and_scope(self, mock_require_scopes, mock_boto3_resource):
        """Test filtering suites by both tag and scope"""
        # Mock user identity
        mock_require_scopes.return_value = (
            {
                'identity': 'test@example.com',
                'scopes': ['api/admin']
            },
            None
        )
        
        # Mock DynamoDB response
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#123',
                    'id': '123',
                    'name': 'Smoke Tests',
                    'scope': 'suite:smoke-tests',
                    'tags': ['smoke', 'critical']
                },
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#456',
                    'id': '456',
                    'name': 'Other Smoke Tests',
                    'scope': 'suite:other',
                    'tags': ['smoke']
                }
            ]
        }
        
        # Call handler with both filters
        event = {'queryStringParameters': {'tag': 'smoke', 'scope': 'suite:smoke-tests'}}
        response = handler(event, None)
        
        # Verify response - should only return suites matching both filters
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['suites']) == 1
        assert body['suites'][0]['name'] == 'Smoke Tests'
    
    @patch('list_test_suites.require_scopes')
    def test_list_suites_unauthorized(self, mock_require_scopes):
        """Test that unauthorized requests are rejected"""
        # Mock authorization failure
        mock_require_scopes.return_value = (
            None,
            {
                'statusCode': 403,
                'body': json.dumps({'error': 'Forbidden'})
            }
        )
        
        # Call handler
        event = {'queryStringParameters': None}
        response = handler(event, None)
        
        # Verify error response
        assert response['statusCode'] == 403
    
    @patch('list_test_suites.boto3.resource')
    @patch('list_test_suites.require_scopes')
    def test_list_suites_empty_result(self, mock_require_scopes, mock_boto3_resource):
        """Test listing when no suites exist"""
        # Mock user identity
        mock_require_scopes.return_value = (
            {
                'identity': 'test@example.com',
                'scopes': ['api/suite.read']
            },
            None
        )
        
        # Mock empty DynamoDB response
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {'Items': []}
        
        # Call handler
        event = {'queryStringParameters': None}
        response = handler(event, None)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['suites'] == []
    
    @patch('list_test_suites.boto3.resource')
    @patch('list_test_suites.require_scopes')
    def test_list_suites_no_accessible_suites(self, mock_require_scopes, mock_boto3_resource):
        """Test when user has api/suite.read - now returns all suites with simplified authorization"""
        # Mock user identity with api/suite.read scope
        mock_require_scopes.return_value = (
            {
                'identity': 'test@example.com',
                'scopes': ['api/suite.read']
            },
            None
        )
        
        # Mock DynamoDB response with suites
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#123',
                    'id': '123',
                    'name': 'Smoke Tests',
                    'scope': 'suite:smoke-tests',
                    'tags': []
                }
            ]
        }
        
        # Call handler
        event = {'queryStringParameters': None}
        response = handler(event, None)
        
        # Verify response - with simplified authorization, user can see all suites
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['suites']) == 1
        assert body['suites'][0]['name'] == 'Smoke Tests'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

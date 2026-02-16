"""Unit tests for validate_scope_access function in utils.py"""
import pytest
from utils import validate_scope_access


class TestValidateScopeAccess:
    """Test suite for validate_scope_access function"""
    
    def test_wildcard_scope_grants_all_permissions(self):
        """Test that wildcard scope grants all permissions"""
        user_scopes = ['suite:smoke-tests:*']
        
        # Should not raise for any permission type
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'read')
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'write')
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'execute')
    
    def test_specific_permission_grants_access(self):
        """Test that specific permission grants access"""
        user_scopes = ['suite:smoke-tests:read']
        
        # Should not raise for read permission
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'read')
    
    def test_write_implies_read(self):
        """Test that write permission implies read permission"""
        user_scopes = ['suite:smoke-tests:write']
        
        # Should not raise for read permission
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'read')
    
    def test_write_implies_execute(self):
        """Test that write permission implies execute permission"""
        user_scopes = ['suite:smoke-tests:write']
        
        # Should not raise for execute permission
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'execute')
    
    def test_read_does_not_imply_write(self):
        """Test that read permission does not imply write permission"""
        user_scopes = ['suite:smoke-tests:read']
        
        # Should raise for write permission
        with pytest.raises(PermissionError, match='User lacks write permission on suite:smoke-tests'):
            validate_scope_access(user_scopes, 'suite:smoke-tests', 'write')
    
    def test_read_does_not_imply_execute(self):
        """Test that read permission does not imply execute permission"""
        user_scopes = ['suite:smoke-tests:read']
        
        # Should raise for execute permission
        with pytest.raises(PermissionError, match='User lacks execute permission on suite:smoke-tests'):
            validate_scope_access(user_scopes, 'suite:smoke-tests', 'execute')
    
    def test_execute_does_not_imply_write(self):
        """Test that execute permission does not imply write permission"""
        user_scopes = ['suite:smoke-tests:execute']
        
        # Should raise for write permission
        with pytest.raises(PermissionError, match='User lacks write permission on suite:smoke-tests'):
            validate_scope_access(user_scopes, 'suite:smoke-tests', 'write')
    
    def test_no_matching_scope_raises_error(self):
        """Test that missing scope raises PermissionError"""
        user_scopes = ['suite:other-suite:read']
        
        # Should raise for different scope
        with pytest.raises(PermissionError, match='User lacks read permission on suite:smoke-tests'):
            validate_scope_access(user_scopes, 'suite:smoke-tests', 'read')
    
    def test_empty_scopes_raises_error(self):
        """Test that empty scopes list raises PermissionError"""
        user_scopes = []
        
        # Should raise for any permission
        with pytest.raises(PermissionError, match='User lacks read permission on suite:smoke-tests'):
            validate_scope_access(user_scopes, 'suite:smoke-tests', 'read')
    
    def test_usecase_scope_pattern(self):
        """Test that usecase scope pattern works"""
        user_scopes = ['usecase:login:read']
        
        # Should not raise for read permission
        validate_scope_access(user_scopes, 'usecase:login', 'read')
    
    def test_usecase_wildcard_scope(self):
        """Test that usecase wildcard scope works"""
        user_scopes = ['usecase:login:*']
        
        # Should not raise for any permission
        validate_scope_access(user_scopes, 'usecase:login', 'read')
        validate_scope_access(user_scopes, 'usecase:login', 'write')
        validate_scope_access(user_scopes, 'usecase:login', 'execute')
    
    def test_multiple_scopes_first_match_wins(self):
        """Test that having multiple scopes works correctly"""
        user_scopes = ['suite:other:read', 'suite:smoke-tests:write', 'suite:another:execute']
        
        # Should not raise because write is present
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'read')
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'write')
        validate_scope_access(user_scopes, 'suite:smoke-tests', 'execute')
    
    def test_scope_with_hyphens(self):
        """Test that scopes with hyphens work correctly"""
        user_scopes = ['suite:smoke-tests-v2:read']
        
        # Should not raise for matching scope with hyphens
        validate_scope_access(user_scopes, 'suite:smoke-tests-v2', 'read')
    
    def test_case_sensitive_scope_matching(self):
        """Test that scope matching is case-sensitive"""
        user_scopes = ['suite:Smoke-Tests:read']
        
        # Should raise because scope is case-sensitive
        with pytest.raises(PermissionError, match='User lacks read permission on suite:smoke-tests'):
            validate_scope_access(user_scopes, 'suite:smoke-tests', 'read')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

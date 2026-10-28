"""
Property-based tests for OAuth Client Management endpoints.

Feature: wp1d-oauth-client-management
Tests universal correctness properties across all valid inputs using hypothesis.
"""

import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Import handlers
import create_oauth_client
import list_oauth_clients
import delete_oauth_client
import rotate_client_secret
from role_scopes import M2M_FORBIDDEN_SCOPES

TEAM_ID = 'team-1'
EDITOR_IN_TEAM = [{'team_id': TEAM_ID, 'role': 'editor'}]


@pytest.fixture(autouse=True, scope='module')
def _team_exists():
    """create_oauth_client checks the team exists; never touch real DynamoDB."""
    with patch('permissions_repo.get_team', return_value={'id': TEAM_ID, 'name': 'Team 1'}):
        yield


# Test data generators
VALID_SCOPES = [
    'api/suite.read',
    'api/suite.write',
    'api/execution.read',
    'api/execution.write',
    'api/usecases.read',
    'api/usecases.write',
    'api/oauth-clients.read',
    'api/oauth-clients.write',
    'api/admin'
]


@st.composite
def user_scope_set(draw):
    """Generate a random set of user scopes."""
    scopes = draw(st.lists(
        st.sampled_from(VALID_SCOPES),
        min_size=1,
        max_size=len(VALID_SCOPES),
        unique=True
    ))
    return scopes


@st.composite
def oauth_client_name(draw):
    """Generate a valid OAuth client name."""
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters=' -_'),
        min_size=1,
        max_size=100
    ))
    # Verify name is not just whitespace
    assume(name.strip())
    return name.strip()


@st.composite
def requested_scope_set(draw):
    """Generate a random set of requested scopes."""
    scopes = draw(st.lists(
        st.sampled_from(VALID_SCOPES),
        min_size=1,
        max_size=7,
        unique=True
    ))
    return scopes


def create_mock_event(user_scopes, body=None, path_params=None, team_roles=EDITOR_IN_TEAM):
    """Create a mock API Gateway event with user scopes (editor in TEAM_ID by default)."""
    event = {
        'requestContext': {
            'authorizer': {
                'claims': {
                    'sub': 'test-user-123',
                    'email': 'test@example.com',
                    'scope': ' '.join(user_scopes),  # Space-separated scopes
                    'teamRoles': json.dumps(team_roles),
                }
            }
        },
        'headers': {},
        'pathParameters': path_params or {}
    }
    
    if body:
        event['body'] = json.dumps(body)
    
    return event


# Property 1: Scope Validation Prevents Privilege Escalation
@given(
    user_scopes=user_scope_set(),
    requested_scopes=requested_scope_set(),
    client_name=oauth_client_name()
)
@settings(max_examples=100, deadline=None)
@patch.dict(os.environ, {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'})
@patch('create_oauth_client.boto3.client')
@patch('create_oauth_client.boto3.resource')
def test_property_1_scope_validation_prevents_privilege_escalation(
    mock_resource, mock_client, user_scopes, requested_scopes, client_name
):
    """
    Feature: wp1d-oauth-client-management, Property 1: Scope Validation Prevents Privilege Escalation
    
    **Validates: Requirements US1.3**
    
    For any user with a set of scopes S and any requested set of scopes R,
    creating an OAuth client with scopes R should succeed if and only if
    R ⊆ S or the user has the 'api/admin' scope.
    """
    # Setup mocks
    mock_cognito = MagicMock()
    mock_client.return_value = mock_cognito
    
    # Mock Amazon Cognito resource server response
    mock_cognito.describe_resource_server.return_value = {
        'ResourceServer': {
            'Scopes': [
                {'ScopeName': scope.split('/')[-1], 'ScopeDescription': f'Scope {scope}'}
                for scope in VALID_SCOPES
            ]
        }
    }
    
    # Mock Amazon Cognito client creation
    mock_cognito.create_user_pool_client.return_value = {
        'UserPoolClient': {
            'ClientId': 'test-client-id',
            'ClientSecret': 'test-secret',
            'ClientName': client_name,
            'CreationDate': datetime.now()
        }
    }
    
    # Mock DynamoDB
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_resource.return_value = mock_dynamodb
    mock_dynamodb.Table.return_value = mock_table
    
    # Verify user has oauth-clients.write scope to call the endpoint
    # (this is separate from the privilege escalation check)
    user_scopes_with_write = list(set(user_scopes + ['api/oauth-clients.write']))
    
    # Create event
    event = create_mock_event(user_scopes_with_write, body={
        'name': client_name,
        'scopes': requested_scopes,
        'teamId': TEAM_ID,
    })
    
    # Execute handler
    response = create_oauth_client.handler(event, None)
    status_code = response['statusCode']
    
    # Verify property
    has_admin = 'api/admin' in user_scopes_with_write
    all_scopes_granted = all(scope in user_scopes_with_write for scope in requested_scopes)
    
    if set(requested_scopes) & M2M_FORBIDDEN_SCOPES:
        # M2M clients may never hold admin / team-management scopes
        assert status_code == 400, f"Expected 400 for forbidden scopes, got {status_code}"
        mock_cognito.create_user_pool_client.assert_not_called()
    elif has_admin or all_scopes_granted:
        # Should succeed
        assert status_code == 201, f"Expected 201 but got {status_code}. User scopes: {user_scopes_with_write}, Requested: {requested_scopes}"
    else:
        # Should fail with 403 (privilege escalation attempt)
        assert status_code == 403, f"Expected 403 but got {status_code}. User scopes: {user_scopes_with_write}, Requested: {requested_scopes}"
        body = json.loads(response['body'])
        assert 'error' in body or 'message' in body


# Property 2: Client Credentials Generation
@given(
    user_scopes=user_scope_set(),
    client_name=oauth_client_name()
)
@settings(max_examples=100, deadline=None)
@patch.dict(os.environ, {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'})
@patch('create_oauth_client.boto3.client')
@patch('create_oauth_client.boto3.resource')
def test_property_2_client_credentials_generation(
    mock_resource, mock_client, user_scopes, client_name
):
    """
    Feature: wp1d-oauth-client-management, Property 2: Client Credentials Generation
    
    **Validates: Requirements US1.4**
    
    For any successful OAuth client creation, the response must contain
    both a non-empty client_id and a non-empty client_secret.
    """
    # Setup mocks
    mock_cognito = MagicMock()
    mock_client.return_value = mock_cognito
    
    # Mock Amazon Cognito resource server response
    mock_cognito.describe_resource_server.return_value = {
        'ResourceServer': {
            'Scopes': [
                {'ScopeName': scope.split('/')[-1], 'ScopeDescription': f'Scope {scope}'}
                for scope in VALID_SCOPES
            ]
        }
    }
    
    # Mock Amazon Cognito client creation
    mock_cognito.create_user_pool_client.return_value = {
        'UserPoolClient': {
            'ClientId': 'test-client-id-123',
            'ClientSecret': 'test-secret-xyz789',
            'ClientName': client_name,
            'CreationDate': datetime.now(),
            'RefreshTokenValidity': 30,
            'AccessTokenValidity': 60,
            'IdTokenValidity': 60
        }
    }
    
    # Mock DynamoDB
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_resource.return_value = mock_dynamodb
    mock_dynamodb.Table.return_value = mock_table
    
    # Verify user has oauth-clients.write scope
    user_scopes_with_write = list(set(user_scopes + ['api/oauth-clients.write']))
    
    # Use scopes that user has (to verify success)
    requested_scopes = user_scopes_with_write[:min(3, len(user_scopes_with_write))]
    
    # Create event
    event = create_mock_event(user_scopes_with_write, body={
        'name': client_name,
        'scopes': requested_scopes,
        'teamId': TEAM_ID,
    })
    
    # Execute handler
    response = create_oauth_client.handler(event, None)
    
    # Only verify property if creation succeeded
    if response['statusCode'] == 201:
        body = json.loads(response['body'])
        
        # Verify property: both client_id and client_secret must be present and non-empty
        assert 'client_id' in body, "Response missing client_id"
        assert 'client_secret' in body, "Response missing client_secret"
        assert body['client_id'], "client_id is empty"
        assert body['client_secret'], "client_secret is empty"
        assert len(body['client_id']) > 0, "client_id has zero length"
        assert len(body['client_secret']) > 0, "client_secret has zero length"


# Property 3: Secret Confidentiality
@given(
    user_scopes=st.just(['api/oauth-clients.read', 'api/oauth-clients.write'])
)
@settings(max_examples=50, deadline=None)
@patch.dict(os.environ, {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'})
@patch('list_oauth_clients.boto3.client')
@patch('list_oauth_clients.boto3.resource')
def test_property_3_secret_confidentiality(
    mock_resource, mock_client, user_scopes
):
    """
    Feature: wp1d-oauth-client-management, Property 3: Secret Confidentiality
    
    **Validates: Requirements US1.5, US2.3, US4.3**
    
    For any OAuth client, after creation or rotation, calling the list endpoint
    should never return the client_secret field in the response.
    """
    # Setup mocks
    mock_cognito = MagicMock()
    mock_client.return_value = mock_cognito
    
    # Mock list user pool clients
    mock_cognito.list_user_pool_clients.return_value = {
        'UserPoolClients': [
            {'ClientId': 'client-1'},
            {'ClientId': 'client-2'},
            {'ClientId': 'client-3'}
        ]
    }
    
    # Mock describe user pool client (should NOT include ClientSecret)
    def describe_client_side_effect(UserPoolId, ClientId):
        return {
            'UserPoolClient': {
                'ClientId': ClientId,
                'ClientName': f'Test Client {ClientId}',
                'CreationDate': datetime.now(),
                'LastModifiedDate': datetime.now(),
                'AllowedOAuthFlows': ['client_credentials'],
                'AllowedOAuthScopes': ['api/suite.read'],
                'RefreshTokenValidity': 30,
                'AccessTokenValidity': 60,
                'IdTokenValidity': 60
                # NOTE: ClientSecret is intentionally NOT included here
            }
        }
    
    mock_cognito.describe_user_pool_client.side_effect = describe_client_side_effect
    
    # Mock DynamoDB
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_resource.return_value = mock_dynamodb
    mock_dynamodb.Table.return_value = mock_table
    
    # OAUTH_CLIENTS records (bound to the caller's team so they are visible)
    mock_table.query.return_value = {'Items': [
        {'sk': cid, 'created_by': 'test@example.com', 'team_id': TEAM_ID}
        for cid in ('client-1', 'client-2', 'client-3')
    ]}
    
    # Create event
    event = create_mock_event(user_scopes)
    
    # Execute handler
    response = list_oauth_clients.handler(event, None)
    
    # Verify property
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    
    # Verify no client_secret in any client object
    assert 'clients' in body
    for client in body['clients']:
        assert 'client_secret' not in client, f"client_secret found in list response for client {client.get('client_id')}"
        assert 'ClientSecret' not in client, f"ClientSecret found in list response for client {client.get('client_id')}"


# Property 4: Amazon Cognito Registration
@given(
    user_scopes=user_scope_set(),
    client_name=oauth_client_name()
)
@settings(max_examples=100, deadline=None)
@patch.dict(os.environ, {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'})
@patch('create_oauth_client.boto3.client')
@patch('create_oauth_client.boto3.resource')
def test_property_4_cognito_registration(
    mock_resource, mock_client, user_scopes, client_name
):
    """
    Feature: wp1d-oauth-client-management, Property 4: Amazon Cognito Registration
    
    **Validates: Requirements US1.6**
    
    For any successfully created OAuth client with client_id C,
    querying Amazon Cognito for client C should return the client configuration.
    """
    # Setup mocks
    mock_cognito = MagicMock()
    mock_client.return_value = mock_cognito
    
    # Mock Amazon Cognito resource server response
    mock_cognito.describe_resource_server.return_value = {
        'ResourceServer': {
            'Scopes': [
                {'ScopeName': scope.split('/')[-1], 'ScopeDescription': f'Scope {scope}'}
                for scope in VALID_SCOPES
            ]
        }
    }
    
    # Track created clients
    created_clients = {}
    
    def create_client_side_effect(**kwargs):
        client_id = f"client-{len(created_clients)}"
        client_data = {
            'ClientId': client_id,
            'ClientSecret': f'secret-{client_id}',
            'ClientName': kwargs.get('ClientName'),
            'CreationDate': datetime.now(),
            'AllowedOAuthScopes': kwargs.get('AllowedOAuthScopes', []),
            'AllowedOAuthFlows': kwargs.get('AllowedOAuthFlows', []),
            'RefreshTokenValidity': 30,
            'AccessTokenValidity': 60,
            'IdTokenValidity': 60
        }
        created_clients[client_id] = client_data
        return {'UserPoolClient': client_data}
    
    mock_cognito.create_user_pool_client.side_effect = create_client_side_effect
    
    # Mock DynamoDB
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_resource.return_value = mock_dynamodb
    mock_dynamodb.Table.return_value = mock_table
    
    # Use scopes that user has
    requested_scopes = user_scopes[:min(3, len(user_scopes))]
    
    # Create event
    event = create_mock_event(user_scopes, body={
        'name': client_name,
        'scopes': requested_scopes,
        'teamId': TEAM_ID,
    })
    
    # Execute handler
    response = create_oauth_client.handler(event, None)
    
    # Only verify property if creation succeeded
    if response['statusCode'] == 201:
        body = json.loads(response['body'])
        client_id = body['client_id']
        
        # Verify property: client should exist in our "Amazon Cognito" (mocked storage)
        assert client_id in created_clients, f"Client {client_id} not found in Amazon Cognito after creation"
        
        # Verify client configuration matches
        cognito_client = created_clients[client_id]
        assert cognito_client['ClientName'] == client_name
        assert set(cognito_client['AllowedOAuthScopes']) == set(requested_scopes)


# Property 5: List Response Completeness
@given(
    user_scopes=st.just(['api/oauth-clients.read'])
)
@settings(max_examples=50, deadline=None)
@patch.dict(os.environ, {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'})
@patch('list_oauth_clients.boto3.client')
@patch('list_oauth_clients.boto3.resource')
def test_property_5_list_response_completeness(
    mock_resource, mock_client, user_scopes
):
    """
    Feature: wp1d-oauth-client-management, Property 5: List Response Completeness
    
    **Validates: Requirements US2.2**
    
    For any OAuth client in the system, the list endpoint response should include
    client_id, client_name, created_date, and allowed_oauth_scopes fields for that client.
    """
    # Setup mocks
    mock_cognito = MagicMock()
    mock_client.return_value = mock_cognito
    
    # Mock list user pool clients
    mock_cognito.list_user_pool_clients.return_value = {
        'UserPoolClients': [
            {'ClientId': 'client-1'},
            {'ClientId': 'client-2'}
        ]
    }
    
    # Mock describe user pool client
    def describe_client_side_effect(UserPoolId, ClientId):
        return {
            'UserPoolClient': {
                'ClientId': ClientId,
                'ClientName': f'Test Client {ClientId}',
                'CreationDate': datetime.now(),
                'LastModifiedDate': datetime.now(),
                'AllowedOAuthFlows': ['client_credentials'],
                'AllowedOAuthScopes': ['api/suite.read', 'api/suite.write'],
                'RefreshTokenValidity': 30,
                'AccessTokenValidity': 60,
                'IdTokenValidity': 60,
                'TokenValidityUnits': {},
                'ExplicitAuthFlows': []
            }
        }
    
    mock_cognito.describe_user_pool_client.side_effect = describe_client_side_effect
    
    # Mock DynamoDB
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_resource.return_value = mock_dynamodb
    mock_dynamodb.Table.return_value = mock_table
    mock_table.query.return_value = {'Items': [
        {'sk': cid, 'created_by': 'test@example.com', 'team_id': TEAM_ID}
        for cid in ('client-1', 'client-2')
    ]}
    
    # Create event
    event = create_mock_event(user_scopes)
    
    # Execute handler
    response = list_oauth_clients.handler(event, None)
    
    # Verify property
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    
    assert 'clients' in body
    assert len(body['clients']) == 2
    for client in body['clients']:
        # Verify all required fields are present
        assert 'client_id' in client, "Missing client_id"
        assert 'client_name' in client, "Missing client_name"
        assert 'created_date' in client, "Missing created_date"
        assert 'allowed_oauth_scopes' in client, "Missing allowed_oauth_scopes"
        
        # Verify fields are not None or empty
        assert client['client_id'], "client_id is empty"
        assert client['client_name'], "client_name is empty"
        assert isinstance(client['allowed_oauth_scopes'], list), "allowed_oauth_scopes is not a list"


# Property 6: Ownership Verification
@given(
    client_name=oauth_client_name()
)
@settings(max_examples=50, deadline=None)
@patch.dict(os.environ, {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'})
@patch('delete_oauth_client.boto3.client')
@patch('delete_oauth_client.boto3.resource')
def test_property_6_ownership_verification(
    mock_resource, mock_client, client_name
):
    """
    Feature: wp1d-oauth-client-management, Property 6: Ownership Verification
    
    **Validates: Requirements US3.1**
    
    For any OAuth client created by user A, user A should be able to delete the client,
    and any user B (where B ≠ A and B does not have admin scope) should receive a 403
    error when attempting to delete the client.
    """
    # Setup mocks
    mock_cognito = MagicMock()
    mock_client.return_value = mock_cognito
    
    # Mock DynamoDB
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_resource.return_value = mock_dynamodb
    mock_dynamodb.Table.return_value = mock_table
    
    client_id = 'test-client-123'
    owner_email = 'owner@example.com'
    
    # Mock DynamoDB get_item to return metadata with owner
    mock_table.get_item.return_value = {
        'Item': {
            'client_id': client_id,
            'created_by': owner_email
        }
    }
    
    # Test 1: Owner can delete (should succeed or at least not fail with 403)
    owner_scopes = ['api/oauth-clients.write']
    owner_event = create_mock_event(owner_scopes, path_params={'clientId': client_id})
    owner_event['requestContext']['authorizer']['claims']['email'] = owner_email
    
    # Note: We're testing the ownership check logic, not the full deletion
    # The actual deletion would succeed for the owner
    # For this test, we verify that non-owners get 403
    
    # Test 2: Non-owner without admin cannot delete (should fail with 403)
    non_owner_scopes = ['api/oauth-clients.write']  # Has permission but not owner
    non_owner_event = create_mock_event(non_owner_scopes, path_params={'clientId': client_id})
    non_owner_event['requestContext']['authorizer']['claims']['email'] = 'other@example.com'
    
    # Execute handler for non-owner
    response = delete_oauth_client.handler(non_owner_event, None)
    
    # Verify property: a non-owner (not team lead, not admin) is denied
    assert response['statusCode'] == 403
    mock_cognito.delete_user_pool_client.assert_not_called()

    # The owner can delete
    response = delete_oauth_client.handler(owner_event, None)
    assert response['statusCode'] == 204


# Property 7: Immediate Revocation
@given(
    client_name=oauth_client_name()
)
@settings(max_examples=50, deadline=None)
@patch.dict(os.environ, {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'})
@patch('delete_oauth_client.boto3.client')
@patch('delete_oauth_client.boto3.resource')
def test_property_7_immediate_revocation(
    mock_resource, mock_client, client_name
):
    """
    Feature: wp1d-oauth-client-management, Property 7: Immediate Revocation
    
    **Validates: Requirements US3.3, US3.4**
    
    For any deleted OAuth client with credentials (client_id, client_secret),
    attempting to authenticate with those credentials should fail immediately after deletion.
    """
    # Setup mocks
    mock_cognito = MagicMock()
    mock_client.return_value = mock_cognito
    
    # Mock DynamoDB
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_resource.return_value = mock_dynamodb
    mock_dynamodb.Table.return_value = mock_table
    
    client_id = 'test-client-456'
    
    # Mock DynamoDB get_item to return metadata
    mock_table.get_item.return_value = {
        'Item': {
            'client_id': client_id,
            'created_by': 'test@example.com'
        }
    }
    
    # Track if client was deleted from Amazon Cognito
    deleted_clients = []
    
    def delete_client_side_effect(UserPoolId, ClientId):
        deleted_clients.append(ClientId)
        return {}
    
    mock_cognito.delete_user_pool_client.side_effect = delete_client_side_effect
    
    # Create event
    user_scopes = ['api/oauth-clients.write']
    event = create_mock_event(user_scopes, path_params={'clientId': client_id})
    
    # Execute handler
    response = delete_oauth_client.handler(event, None)
    
    # Verify property: if deletion succeeded, client should be deleted from Amazon Cognito
    assert response['statusCode'] == 204
    if response['statusCode'] == 204:
        assert client_id in deleted_clients, f"Client {client_id} was not deleted from Amazon Cognito"
        # In real implementation, this would mean immediate revocation
        # The client can no longer authenticate



# ---------------------------------------------------------------------------
# Team binding (H-2): unit tests
# ---------------------------------------------------------------------------

_ENV = {'USER_POOL_ID': 'test-pool', 'TABLE_NAME': 'test-table'}


def _cognito_for_create(mock_client):
    cognito = MagicMock()
    mock_client.return_value = cognito
    cognito.describe_resource_server.return_value = {'ResourceServer': {'Scopes': [
        {'ScopeName': s.split('/')[-1]} for s in VALID_SCOPES + ['api/usecases.execute', 'api/teams.manage']]}}
    cognito.create_user_pool_client.return_value = {'UserPoolClient': {
        'ClientId': 'new-client', 'ClientSecret': 'secret', 'ClientName': 'ci', 'CreationDate': datetime.now()}}
    return cognito


@patch.dict(os.environ, _ENV)
@patch('create_oauth_client.boto3.resource')
@patch('create_oauth_client.boto3.client')
class TestCreateOAuthClientTeamBinding:
    def _call(self, team_roles, body, scopes=('api/oauth-clients.write', 'api/usecases.execute')):
        return create_oauth_client.handler(create_mock_event(list(scopes), body=body, team_roles=team_roles), None)

    def test_team_id_required(self, mock_client, mock_resource):
        cognito = _cognito_for_create(mock_client)
        resp = self._call(EDITOR_IN_TEAM, {'name': 'ci', 'scopes': ['api/usecases.execute']})
        assert resp['statusCode'] == 400
        assert json.loads(resp['body'])['error'] == 'teamId is required'
        cognito.create_user_pool_client.assert_not_called()

    @pytest.mark.parametrize('team_roles', [
        [], [{'team_id': TEAM_ID, 'role': 'executor'}], [{'team_id': TEAM_ID, 'role': 'viewer'}],
        [{'team_id': 'other-team', 'role': 'team_lead'}],
    ])
    def test_caller_without_editor_role_in_team_gets_403(self, mock_client, mock_resource, team_roles):
        cognito = _cognito_for_create(mock_client)
        resp = self._call(team_roles, {'name': 'ci', 'scopes': ['api/usecases.execute'], 'teamId': TEAM_ID})
        assert resp['statusCode'] == 403
        cognito.create_user_pool_client.assert_not_called()

    def test_unknown_team_gets_404(self, mock_client, mock_resource):
        _cognito_for_create(mock_client)
        with patch('permissions_repo.get_team', return_value=None):
            resp = self._call(EDITOR_IN_TEAM, {'name': 'ci', 'scopes': ['api/usecases.execute'], 'teamId': TEAM_ID})
        assert resp['statusCode'] == 404

    @pytest.mark.parametrize('forbidden', ['api/admin', 'api/teams.manage'])
    def test_forbidden_scopes_refused_even_for_admin(self, mock_client, mock_resource, forbidden):
        cognito = _cognito_for_create(mock_client)
        resp = self._call([], {'name': 'ci', 'scopes': [forbidden], 'teamId': TEAM_ID},
                          scopes=('api/admin',))
        assert resp['statusCode'] == 400
        cognito.create_user_pool_client.assert_not_called()

    @pytest.mark.parametrize('caller_role', ['editor', 'team_lead'])
    def test_binding_stored_with_role_capped_at_editor(self, mock_client, mock_resource, caller_role):
        _cognito_for_create(mock_client)
        table = mock_resource.return_value.Table.return_value
        resp = self._call([{'team_id': TEAM_ID, 'role': caller_role}],
                          {'name': 'ci', 'scopes': ['api/usecases.execute'], 'teamId': TEAM_ID})
        assert resp['statusCode'] == 201
        item = table.put_item.call_args.kwargs['Item']
        assert (item['pk'], item['sk']) == ('OAUTH_CLIENTS', 'new-client')
        assert item['team_id'] == TEAM_ID and item['team_role'] == 'editor'
        assert json.loads(resp['body'])['team_id'] == TEAM_ID

    def test_admin_binds_any_team_as_editor(self, mock_client, mock_resource):
        _cognito_for_create(mock_client)
        table = mock_resource.return_value.Table.return_value
        resp = self._call([], {'name': 'ci', 'scopes': ['api/usecases.execute'], 'teamId': TEAM_ID},
                          scopes=('api/admin',))
        assert resp['statusCode'] == 201
        assert table.put_item.call_args.kwargs['Item']['team_role'] == 'editor'


def test_bound_team_role_never_above_editor():
    for role, expected in [('team_lead', 'editor'), ('editor', 'editor'), ('executor', 'executor'),
                           ('viewer', 'viewer')]:
        identity = {'team_roles': [{'team_id': 't', 'role': role}]}
        assert create_oauth_client.bound_team_role(identity, 't') == expected
    assert create_oauth_client.bound_team_role({'team_roles': []}, 't') == 'editor'


def _list_cognito(mock_client, client_ids):
    cognito = MagicMock()
    mock_client.return_value = cognito
    cognito.list_user_pool_clients.return_value = {'UserPoolClients': [{'ClientId': c} for c in client_ids]}
    cognito.describe_user_pool_client.side_effect = lambda UserPoolId, ClientId: {
        'UserPoolClient': {'ClientId': ClientId, 'ClientName': ClientId, 'CreationDate': datetime.now()}}
    return cognito


@patch.dict(os.environ, _ENV)
@patch('list_oauth_clients.boto3.resource')
@patch('list_oauth_clients.boto3.client')
class TestListOAuthClientsTeamFilter:
    RECORDS = [
        {'sk': 'c-team1', 'created_by': 'a@example.com', 'team_id': TEAM_ID},
        {'sk': 'c-team2', 'created_by': 'b@example.com', 'team_id': 'team-2'},
        {'sk': 'c-unbound', 'created_by': 'c@example.com'},
    ]

    def _ids(self, mock_client, mock_resource, team_roles, scopes=('api/oauth-clients.read',)):
        cognito = _list_cognito(mock_client, ['c-team1', 'c-team2', 'c-unbound', 'web-client'])
        mock_resource.return_value.Table.return_value.query.return_value = {'Items': self.RECORDS}
        resp = list_oauth_clients.handler(create_mock_event(list(scopes), team_roles=team_roles), None)
        assert resp['statusCode'] == 200
        return [c['client_id'] for c in json.loads(resp['body'])['clients']], cognito

    def test_editor_sees_only_own_team_clients(self, mock_client, mock_resource):
        ids, cognito = self._ids(mock_client, mock_resource, EDITOR_IN_TEAM)
        assert ids == ['c-team1']
        assert cognito.describe_user_pool_client.call_count == 1

    def test_viewer_sees_nothing(self, mock_client, mock_resource):
        ids, _ = self._ids(mock_client, mock_resource, [{'team_id': TEAM_ID, 'role': 'viewer'}])
        assert ids == []

    def test_admin_sees_all(self, mock_client, mock_resource):
        ids, _ = self._ids(mock_client, mock_resource, [], scopes=('api/admin',))
        assert ids == ['c-team1', 'c-team2', 'c-unbound', 'web-client']

    def test_team_id_in_response(self, mock_client, mock_resource):
        _list_cognito(mock_client, ['c-team1'])
        mock_resource.return_value.Table.return_value.query.return_value = {'Items': self.RECORDS}
        resp = list_oauth_clients.handler(create_mock_event(['api/oauth-clients.read']), None)
        assert json.loads(resp['body'])['clients'][0]['team_id'] == TEAM_ID


_CLIENT_RECORD = {'client_id': 'c-1', 'client_name': 'ci', 'created_by': 'owner@example.com',
                  'team_id': TEAM_ID, 'team_role': 'editor', 'created_at': '2026-01-01'}


def _manage_event(email, team_roles, scopes=('api/oauth-clients.write',)):
    event = create_mock_event(list(scopes), path_params={'clientId': 'c-1'}, team_roles=team_roles)
    event['requestContext']['authorizer']['claims']['email'] = email
    return event


_MANAGERS = [
    ('owner@example.com', [], ('api/oauth-clients.write',)),
    ('lead@example.com', [{'team_id': TEAM_ID, 'role': 'team_lead'}], ('api/oauth-clients.write',)),
    ('admin@example.com', [], ('api/admin',)),
]
_NON_MANAGERS = [
    ('editor@example.com', EDITOR_IN_TEAM),
    ('lead2@example.com', [{'team_id': 'team-2', 'role': 'team_lead'}]),
]


@patch.dict(os.environ, _ENV)
@patch('delete_oauth_client.boto3.resource')
@patch('delete_oauth_client.boto3.client')
class TestDeleteOAuthClientOwner:
    @pytest.mark.parametrize('email,team_roles,scopes', _MANAGERS)
    def test_managers_get_204(self, mock_client, mock_resource, email, team_roles, scopes):
        mock_resource.return_value.Table.return_value.get_item.return_value = {'Item': dict(_CLIENT_RECORD)}
        resp = delete_oauth_client.handler(_manage_event(email, team_roles, scopes), None)
        assert resp['statusCode'] == 204 and resp['body'] == ''
        mock_client.return_value.delete_user_pool_client.assert_called_once()

    @pytest.mark.parametrize('email,team_roles', _NON_MANAGERS)
    def test_others_get_403(self, mock_client, mock_resource, email, team_roles):
        mock_resource.return_value.Table.return_value.get_item.return_value = {'Item': dict(_CLIENT_RECORD)}
        resp = delete_oauth_client.handler(_manage_event(email, team_roles), None)
        assert resp['statusCode'] == 403
        mock_client.return_value.delete_user_pool_client.assert_not_called()


def _rotate_cognito(mock_client, scopes=('api/usecases.execute',)):
    cognito = MagicMock()
    mock_client.return_value = cognito
    cognito.describe_user_pool_client.return_value = {'UserPoolClient': {
        'ClientName': 'ci', 'AllowedOAuthScopes': list(scopes)}}
    cognito.create_user_pool_client.return_value = {'UserPoolClient': {
        'ClientId': 'c-2', 'ClientSecret': 'new-secret'}}
    return cognito


@patch.dict(os.environ, _ENV)
@patch('rotate_client_secret.boto3.resource')
@patch('rotate_client_secret.boto3.client')
class TestRotateClientSecretOwner:
    @pytest.mark.parametrize('email,team_roles,scopes', _MANAGERS)
    def test_managers_can_rotate_and_binding_kept(self, mock_client, mock_resource, email, team_roles, scopes):
        _rotate_cognito(mock_client)
        table = mock_resource.return_value.Table.return_value
        table.get_item.return_value = {'Item': dict(_CLIENT_RECORD)}
        resp = rotate_client_secret.handler(_manage_event(email, team_roles, scopes), None)
        assert resp['statusCode'] == 200
        item = table.put_item.call_args.kwargs['Item']
        assert item['sk'] == 'c-2' and item['team_id'] == TEAM_ID and item['team_role'] == 'editor'

    @pytest.mark.parametrize('email,team_roles', _NON_MANAGERS)
    def test_others_get_403(self, mock_client, mock_resource, email, team_roles):
        cognito = _rotate_cognito(mock_client)
        mock_resource.return_value.Table.return_value.get_item.return_value = {'Item': dict(_CLIENT_RECORD)}
        resp = rotate_client_secret.handler(_manage_event(email, team_roles), None)
        assert resp['statusCode'] == 403
        assert 'owner@example.com' not in resp['body']
        cognito.delete_user_pool_client.assert_not_called()

    def test_client_with_forbidden_scope_is_not_recreated(self, mock_client, mock_resource):
        cognito = _rotate_cognito(mock_client, scopes=('api/admin',))
        mock_resource.return_value.Table.return_value.get_item.return_value = {'Item': dict(_CLIENT_RECORD)}
        resp = rotate_client_secret.handler(_manage_event('admin@example.com', [], ('api/admin',)), None)
        assert resp['statusCode'] == 400
        cognito.delete_user_pool_client.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

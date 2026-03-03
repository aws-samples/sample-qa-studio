"""Unit tests for get_usecase_secret_value Lambda function."""

import unittest
import json
import os
from unittest.mock import patch, MagicMock

from get_usecase_secret_value import handler


class TestGetUsecaseSecretValue(unittest.TestCase):
    """Unit tests for the secret value retrieval endpoint."""

    def setUp(self):
        os.environ['SECRET_PREFIX'] = 'test-prefix'

    def _build_event(self, usecase_id='uc-123', secret_key='my_password',
                     scope='api/usecases.read'):
        return {
            'pathParameters': {
                'id': usecase_id,
                'secret_key': secret_key,
            },
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': scope,
                }
            },
        }

    @patch('get_usecase_secret_value.boto3')
    def test_success_returns_secret_value(self, mock_boto3):
        """Returns the decrypted secret value."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 's3cret_v@lue'
        }

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['key'], 'my_password')
        self.assertEqual(body['value'], 's3cret_v@lue')

        mock_client.get_secret_value.assert_called_once_with(
            SecretId='test-prefix/usecase/uc-123/my_password'
        )

    @patch('get_usecase_secret_value.boto3')
    def test_secret_not_found_returns_404(self, mock_boto3):
        """Returns 404 when secret does not exist in Secrets Manager."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        error_response = {'Error': {'Code': 'ResourceNotFoundException',
                                     'Message': 'not found'}}
        mock_client.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_client.get_secret_value.side_effect = (
            mock_client.exceptions.ResourceNotFoundException('not found')
        )

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertIn('not found', body['error'])

    @patch('get_usecase_secret_value.boto3')
    def test_secret_with_no_value_returns_404(self, mock_boto3):
        """Returns 404 when SecretString is None."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {'SecretString': None}

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertIn('no value', body['error'])

    def test_missing_scope_returns_403(self):
        """Missing api/usecases.read scope returns 403."""
        response = handler(self._build_event(scope='api/executions.read'), None)

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])

    def test_missing_usecase_id_returns_400(self):
        """Missing usecase ID returns 400."""
        event = {
            'pathParameters': {'secret_key': 'my_password'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/usecases.read',
                }
            },
        }
        response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing use case ID', body['error'])

    def test_missing_secret_key_returns_400(self):
        """Missing secret_key returns 400."""
        event = {
            'pathParameters': {'id': 'uc-123'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/usecases.read',
                }
            },
        }
        response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing secret key', body['error'])

    @patch('get_usecase_secret_value.boto3')
    def test_secrets_manager_error_returns_500(self, mock_boto3):
        """Generic Secrets Manager error returns 500."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_client.get_secret_value.side_effect = RuntimeError('boom')

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertIn('Failed to retrieve secret value', body['error'])


if __name__ == '__main__':
    unittest.main()

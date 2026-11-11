"""
Secrets Manager naming and listing shared by every secret Lambda.

Secrets live under two namespaces below the deployment prefix (``SECRET_PREFIX``,
see ``utils.get_secret_prefix``):

- ``{prefix}/usecase/{usecase_id}/{key}``      tagged ``usecase_id``
- ``{prefix}/application/{app_id}/{key}``      tagged ``application_id``

The IAM policies in ``lib/lambda-stack.ts`` are scoped to exactly these two
paths, so no Lambda may build a name any other way (``test_secret_names.py``
greps for inline f-strings).
"""
import re
from datetime import datetime
from typing import Any, Dict, List

from botocore.exceptions import ClientError

# Secret keys become part of the Secrets Manager name; keep them to a safe charset.
SECRET_KEY_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')


def usecase_secret_prefix(prefix: str, usecase_id: str) -> str:
    """Name prefix (with trailing slash) of every secret of a use case."""
    return f"{prefix}/usecase/{usecase_id}/"


def usecase_secret_name(prefix: str, usecase_id: str, key: str) -> str:
    return f"{usecase_secret_prefix(prefix, usecase_id)}{key}"


def application_secret_prefix(prefix: str, app_id: str) -> str:
    """Name prefix (with trailing slash) of every secret of an application."""
    return f"{prefix}/application/{app_id}/"


def application_secret_name(prefix: str, app_id: str, key: str) -> str:
    return f"{application_secret_prefix(prefix, app_id)}{key}"


def _created_at(secret: Dict[str, Any]) -> str:
    created = secret.get('CreatedDate')
    if isinstance(created, datetime):
        return created.strftime('%Y-%m-%dT%H:%M:%SZ')
    return ''


def list_secrets_by_tag(client, tag_key: str, tag_value: str, name_prefix: str) -> List[Dict[str, str]]:
    """
    List the secrets tagged ``tag_key=tag_value`` whose name starts with ``name_prefix``.

    Follows ``NextToken`` pagination. The prefix check guards against tag
    collisions (the tag filter alone matches any secret carrying that value).

    Returns:
        ``[{key, secret_name, description, created_at}]`` in API order; ``key`` is
        the name with ``name_prefix`` removed.
    """
    kwargs: Dict[str, Any] = {
        'Filters': [
            {'Key': 'tag-key', 'Values': [tag_key]},
            {'Key': 'tag-value', 'Values': [tag_value]},
        ],
    }
    secrets: List[Dict[str, str]] = []
    while True:
        response = client.list_secrets(**kwargs)
        for secret in response.get('SecretList', []):
            name = secret.get('Name', '')
            if not name.startswith(name_prefix):
                continue
            secrets.append({
                'key': name[len(name_prefix):],
                'secret_name': name,
                'description': secret.get('Description', ''),
                'created_at': _created_at(secret),
            })
        # Only a real token continues: a MagicMock client in tests answers
        # `.get('NextToken')` with a truthy mock and would loop forever.
        next_token = response.get('NextToken')
        if not isinstance(next_token, str) or not next_token:
            return secrets
        kwargs['NextToken'] = next_token


def upsert_secret(client, name: str, value: str, description: str, tags: List[Dict[str, str]]) -> str:
    """
    Create ``name`` with ``value``; when it already exists, update the value.

    Returns:
        ``'created'`` or ``'updated'``.

    Raises:
        ClientError: any Secrets Manager failure other than the secret already
        existing (the caller logs ``utils.aws_error_code`` — never the value).
    """
    try:
        client.create_secret(Name=name, SecretString=value, Description=description, Tags=tags)
        return 'created'
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceExistsException':
            raise
    client.update_secret(SecretId=name, SecretString=value)
    return 'updated'

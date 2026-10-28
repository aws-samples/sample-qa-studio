"""
Permissions repository — DynamoDB operations for team management.

Data model:
- TEAM#{id}/METADATA — team record (name, created_by, created_at)
- TEAMS/TEAM#{id} — index record for listing all teams
- TEAM#{id}/MEMBER#{sub} — membership record (role, added_at)
  - gsi1pk=USER#{sub}, gsi1sk=TEAM#{id} — for querying user's teams
- TEAM#{owner}/SHARE#{target}#{app} — shared access grant
  - gsi2pk=SHAREDWITH#{target}, gsi2sk=GRANT#{grant_id}
- APPLICATION#{id}/METADATA — extended with owner_team_id, gsi2pk, gsi2sk
  - gsi2pk=OWNERTEAM#{team_id}, gsi2sk=APP#{app_id}
- USECASE#{id}/OVERRIDE — test case visibility override
"""

import logging
from typing import Optional
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, generate_uuid7, get_current_timestamp

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USER_TEAMS_INDEX = 'user-teams-index'
TEAM_APPS_INDEX = 'team-apps-index'  # GSI2


def _get_table():
    """Get the DynamoDB table resource."""
    dynamodb = boto3.resource('dynamodb')
    return dynamodb.Table(get_table_name())


def create_team(name: str, created_by: str) -> dict:
    """
    Create a new team.

    Args:
        name: Team display name (must be unique).
        created_by: Sub (user ID) of the creator.

    Returns:
        Dict with the created team record.
    """
    team_id = generate_uuid7()
    now = get_current_timestamp()

    table = _get_table()

    team_record = {
        'pk': f'TEAM#{team_id}',
        'sk': 'METADATA',
        'id': team_id,
        'name': name,
        'created_by': created_by,
        'created_at': now,
    }

    index_record = {
        'pk': 'TEAMS',
        'sk': f'TEAM#{team_id}',
        'id': team_id,
        'name': name,
    }

    # Use a transaction to write both records atomically
    client = boto3.client('dynamodb')

    def to_dynamo(item: dict) -> dict:
        result = {}
        for k, v in item.items():
            if isinstance(v, str):
                result[k] = {'S': v}
            elif isinstance(v, bool):
                result[k] = {'BOOL': v}
            elif isinstance(v, int):
                result[k] = {'N': str(v)}
            elif isinstance(v, list):
                result[k] = {'L': [{'S': i} for i in v]}
        return result

    client.transact_write_items(
        TransactItems=[
            {'Put': {'TableName': get_table_name(), 'Item': to_dynamo(team_record)}},
            {'Put': {'TableName': get_table_name(), 'Item': to_dynamo(index_record)}},
        ]
    )

    logger.info(f"Created team {team_id}: {name}")
    return team_record


def get_team(team_id: str) -> Optional[dict]:
    """
    Get a team by ID.

    Args:
        team_id: Team ID.

    Returns:
        Team dict or None if not found.
    """
    table = _get_table()
    response = table.get_item(Key={'pk': f'TEAM#{team_id}', 'sk': 'METADATA'})
    return response.get('Item')


def list_teams() -> list:
    """
    List all teams.

    Returns:
        List of team summary dicts (id, name).
    """
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq('TEAMS') & Key('sk').begins_with('TEAM#')
    )
    return response.get('Items', [])


def update_team(team_id: str, fields: dict) -> Optional[dict]:
    """
    Update a team's metadata fields.

    Args:
        team_id: Team ID.
        fields: Dict of field names to new values (e.g. {'name': 'New Name'}).

    Returns:
        Updated team dict, or None if team not found.
    """
    if not fields:
        return get_team(team_id)

    table = _get_table()

    update_parts = []
    expression_values = {}
    expression_names = {}

    for i, (key, value) in enumerate(fields.items()):
        attr_name = f'#attr{i}'
        attr_value = f':val{i}'
        update_parts.append(f'{attr_name} = {attr_value}')
        expression_names[attr_name] = key
        expression_values[attr_value] = value

    update_expression = 'SET ' + ', '.join(update_parts)

    try:
        response = table.update_item(
            Key={'pk': f'TEAM#{team_id}', 'sk': 'METADATA'},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
            ConditionExpression='attribute_exists(pk)',
            ReturnValues='ALL_NEW',
        )
        updated = response.get('Attributes')

        # Also update the index record's name if name was changed
        if 'name' in fields:
            table.update_item(
                Key={'pk': 'TEAMS', 'sk': f'TEAM#{team_id}'},
                UpdateExpression='SET #n = :n',
                ExpressionAttributeNames={'#n': 'name'},
                ExpressionAttributeValues={':n': fields['name']},
            )

        logger.info(f"Updated team {team_id}: {list(fields.keys())}")
        return updated
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None


def delete_team(team_id: str) -> dict:
    """
    Delete a team and all associated data.

    Removes: team metadata, index record, all memberships, and orphans owned apps
    (sets owner_team_id=null, removes GSI2 projection).

    Args:
        team_id: Team ID.

    Returns:
        Dict with {deleted_members_count, orphaned_apps_count}.
    """
    table = _get_table()
    client = boto3.client('dynamodb')
    table_name = get_table_name()

    # 1. Query all memberships for this team
    members_response = table.query(
        KeyConditionExpression=Key('pk').eq(f'TEAM#{team_id}') & Key('sk').begins_with('MEMBER#')
    )
    memberships = members_response.get('Items', [])

    # 2. Find all apps owned by this team.
    #    Primary: GSI2 query. Fallback: scan by owner_team_id to catch apps
    #    whose GSI2 projection is missing (e.g. created before the projection
    #    was written). Merge by pk so each app is orphaned exactly once.
    owned_by_pk = {}
    try:
        apps_response = table.query(
            IndexName=TEAM_APPS_INDEX,
            KeyConditionExpression=Key('gsi2pk').eq(f'OWNERTEAM#{team_id}')
        )
        for app in apps_response.get('Items', []):
            owned_by_pk[app.get('pk')] = app
    except Exception as e:
        logger.warning(f"GSI2 query failed (index may not exist yet): {e}")

    try:
        scan_response = table.scan(
            FilterExpression=Key('owner_team_id').eq(team_id) & Key('sk').eq('METADATA')
        )
        for app in scan_response.get('Items', []):
            owned_by_pk.setdefault(app.get('pk'), app)
    except Exception as e:
        logger.warning(f"owner_team_id scan fallback failed: {e}")

    owned_apps = list(owned_by_pk.values())

    # 3. Build transaction items
    transact_items = []

    # Delete team metadata
    transact_items.append({
        'Delete': {
            'TableName': table_name,
            'Key': {'pk': {'S': f'TEAM#{team_id}'}, 'sk': {'S': 'METADATA'}},
        }
    })

    # Delete index record
    transact_items.append({
        'Delete': {
            'TableName': table_name,
            'Key': {'pk': {'S': 'TEAMS'}, 'sk': {'S': f'TEAM#{team_id}'}},
        }
    })

    # Delete all membership items
    for member in memberships:
        transact_items.append({
            'Delete': {
                'TableName': table_name,
                'Key': {
                    'pk': {'S': f'TEAM#{team_id}'},
                    'sk': {'S': f"MEMBER#{member['user_sub']}"},
                },
            }
        })

    # Orphan owned apps: clear owner_team_id + the free-text team label, and
    # remove the GSI2 projection so the app no longer resolves to this team.
    for app in owned_apps:
        app_pk = app.get('pk', f"APPLICATION#{app.get('app_id', app.get('id', ''))}")
        transact_items.append({
            'Update': {
                'TableName': table_name,
                'Key': {'pk': {'S': app_pk}, 'sk': {'S': 'METADATA'}},
                'UpdateExpression': 'SET owner_team_id = :null, team = :empty REMOVE gsi2pk, gsi2sk',
                'ExpressionAttributeValues': {':null': {'NULL': True}, ':empty': {'S': ''}},
            }
        })

    # DynamoDB transactions max 100 items. Batch if needed.
    if len(transact_items) <= 100:
        if transact_items:
            client.transact_write_items(TransactItems=transact_items)
    else:
        # Fall back to batched operations for large teams
        logger.info(f"Team {team_id} has {len(transact_items)} items — using batched delete")
        # Mark team as DELETING first
        table.update_item(
            Key={'pk': f'TEAM#{team_id}', 'sk': 'METADATA'},
            UpdateExpression='SET #s = :s',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': 'DELETING'},
        )
        # Process in batches of 100
        for i in range(0, len(transact_items), 100):
            batch = transact_items[i:i + 100]
            client.transact_write_items(TransactItems=batch)

    logger.info(
        f"Deleted team {team_id}: {len(memberships)} members, {len(owned_apps)} orphaned apps"
    )
    return {
        'deleted_members_count': len(memberships),
        'orphaned_apps_count': len(owned_apps),
    }


def team_name_exists(name: str) -> bool:
    """
    Check if a team with the given name already exists.

    Scans the TEAMS index records for a matching name.

    Args:
        name: Team name to check.

    Returns:
        True if a team with this name exists.
    """
    table = _get_table()

    response = table.query(
        KeyConditionExpression=Key('pk').eq('TEAMS') & Key('sk').begins_with('TEAM#')
    )

    for item in response.get('Items', []):
        if item.get('name', '').lower() == name.lower():
            return True

    return False


def add_membership(team_id: str, user_sub: str, role: str) -> dict:
    """
    Add a user membership to a team.

    Args:
        team_id: Team ID.
        user_sub: Cognito user sub.
        role: Role name (e.g. 'editor', 'viewer').

    Returns:
        Dict with the membership record.
    """
    now = get_current_timestamp()
    table = _get_table()

    membership = {
        'pk': f'TEAM#{team_id}',
        'sk': f'MEMBER#{user_sub}',
        'team_id': team_id,
        'user_sub': user_sub,
        'role': role,
        'added_at': now,
        'gsi1pk': f'USER#{user_sub}',
        'gsi1sk': f'TEAM#{team_id}',
    }

    table.put_item(Item=membership)
    logger.info(f"Added member to team {team_id} as {role}")
    return membership


def list_user_teams(user_sub: str) -> list:
    """
    List all teams a user belongs to.

    Uses the GSI1 (user-teams-index) to find all team memberships.

    Args:
        user_sub: Cognito user sub.

    Returns:
        List of membership dicts.
    """
    table = _get_table()

    response = table.query(
        IndexName=USER_TEAMS_INDEX,
        KeyConditionExpression=Key('gsi1pk').eq(f'USER#{user_sub}')
    )

    memberships = response.get('Items', [])
    # Strip DynamoDB internal keys
    for m in memberships:
        m.pop('pk', None)
        m.pop('sk', None)
        m.pop('gsi1pk', None)
        m.pop('gsi1sk', None)

    return memberships


# ---------------------------------------------------------------------------
# Membership Operations
# ---------------------------------------------------------------------------


def remove_membership(user_sub: str, team_id: str) -> None:
    """
    Remove a user's membership from a team.

    Args:
        user_sub: Cognito user sub.
        team_id: Team ID.
    """
    table = _get_table()
    table.delete_item(Key={'pk': f'TEAM#{team_id}', 'sk': f'MEMBER#{user_sub}'})
    logger.info(f"Removed member from team {team_id}")


def set_member_role(user_sub: str, team_id: str, new_role: str) -> dict:
    """
    Update a member's role in a team.

    Callers validate new_role against role_scopes.TEAM_ROLES. The studio-wide
    last-admin guard lives in the user handlers (global 'admins' group).

    Args:
        user_sub: Cognito user sub.
        team_id: Team ID.
        new_role: New team role (e.g. 'team_lead', 'editor', 'viewer').

    Returns:
        Updated membership dict.

    Raises:
        KeyError: If membership not found.
    """
    table = _get_table()

    # 1. Read current membership
    response = table.get_item(
        Key={'pk': f'TEAM#{team_id}', 'sk': f'MEMBER#{user_sub}'}
    )
    current = response.get('Item')
    if not current:
        raise KeyError(f"Membership not found: {user_sub} in team {team_id}")

    old_role = current.get('role')

    # 2. No-op if same role
    if old_role == new_role:
        return current

    # 3. Update the membership role
    table.update_item(
        Key={'pk': f'TEAM#{team_id}', 'sk': f'MEMBER#{user_sub}'},
        UpdateExpression='SET #r = :r',
        ExpressionAttributeNames={'#r': 'role'},
        ExpressionAttributeValues={':r': new_role},
    )

    current['role'] = new_role
    logger.info(f"Changed role in team {team_id}: {old_role} -> {new_role}")
    return current


def list_team_members(team_id: str) -> list:
    """
    List all members of a team.

    Args:
        team_id: Team ID.

    Returns:
        List of membership dicts.
    """
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq(f'TEAM#{team_id}') & Key('sk').begins_with('MEMBER#')
    )
    return response.get('Items', [])


# ---------------------------------------------------------------------------
# App Ownership Operations
# ---------------------------------------------------------------------------


def set_app_owner(app_id: str, team_id: str) -> dict:
    """
    Set the owning team for an application.

    Updates APPLICATION#{app_id}/METADATA with owner_team_id and GSI2 projection keys.

    Args:
        app_id: Application ID.
        team_id: Team ID to set as owner.

    Returns:
        Updated application metadata dict.
    """
    table = _get_table()
    response = table.update_item(
        Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
        UpdateExpression='SET owner_team_id = :tid, gsi2pk = :gpk, gsi2sk = :gsk',
        ExpressionAttributeValues={
            ':tid': team_id,
            ':gpk': f'OWNERTEAM#{team_id}',
            ':gsk': f'APP#{app_id}',
        },
        ReturnValues='ALL_NEW',
    )
    logger.info(f"Set app {app_id} owner to team {team_id}")
    return response.get('Attributes', {})


def set_app_resources_owner(app_id: str, team_id: str) -> dict:
    """
    Propagate an application's owning team to its associated use cases and
    test suites (all items whose ``application_id`` equals ``app_id``).

    Called on app reassignment. Team-scoped visibility keys off
    ``owner_team_id`` on the use case / suite, so without this cascade a team
    granted a reassigned app still couldn't see resources that were added while
    the app was unowned or owned by a different team (the migration case).

    Args:
        app_id: Application ID whose resources should be re-owned.
        team_id: New owning team ID to stamp onto the resources.

    Returns:
        Dict with counts of updated resources: {'usecases': int, 'suites': int}.
    """
    table = _get_table()
    counts = {'usecases': 0, 'suites': 0}

    def _reassign(list_pk: str, sk_prefix: str, counter_key: str) -> None:
        last_key = None
        while True:
            query_kwargs = {
                'KeyConditionExpression': Key('pk').eq(list_pk) & Key('sk').begins_with(sk_prefix),
            }
            if last_key:
                query_kwargs['ExclusiveStartKey'] = last_key
            response = table.query(**query_kwargs)
            for item in response.get('Items', []):
                if item.get('application_id') == app_id:
                    table.update_item(
                        Key={'pk': item['pk'], 'sk': item['sk']},
                        UpdateExpression='SET owner_team_id = :tid',
                        ExpressionAttributeValues={':tid': team_id},
                    )
                    counts[counter_key] += 1
            last_key = response.get('LastEvaluatedKey')
            if not last_key:
                break

    _reassign('USECASES', 'USECASE#', 'usecases')
    _reassign('TEST_SUITES', 'SUITE#', 'suites')

    logger.info(
        f"Propagated owner_team_id={team_id} to app {app_id} resources: {counts}"
    )
    return counts


def _get_projected(pk: str, sk: str, attributes: tuple) -> Optional[dict]:
    """get_item reading only `attributes` (aliased, so reserved words like
    `status` are safe). Returns the item or None when it does not exist."""
    table = _get_table()
    names = {f'#a{i}': name for i, name in enumerate(attributes)}
    response = table.get_item(
        Key={'pk': pk, 'sk': sk},
        ProjectionExpression=', '.join(['#pk'] + list(names)),
        ExpressionAttributeNames={'#pk': 'pk', **names},
    )
    return response.get('Item')


def get_app_ownership(app_id: str) -> Optional[dict]:
    """
    Read an application's ownership.

    Returns:
        {'owner_team_id': str|None}, or None when the app does not exist.
    """
    item = _get_projected(f'APPLICATION#{app_id}', 'METADATA', ('owner_team_id',))
    if item is None:
        return None
    return {'owner_team_id': item.get('owner_team_id') or None}


def get_app_owner(app_id: str) -> Optional[str]:
    """
    Get the owning team ID for an application.

    Args:
        app_id: Application ID.

    Returns:
        Team ID string, or None if no owner set or app not found.
    """
    ownership = get_app_ownership(app_id)
    return ownership['owner_team_id'] if ownership else None


def get_usecase_owner(usecase_id: str, include_creator: bool = False) -> Optional[dict]:
    """
    Read the ownership fields of a use case (USECASES/USECASE#{id}).

    Args:
        usecase_id: Use case ID.
        include_creator: Also read USECASE#{id}/CREATED_BY for the
            creator-retains-edit rule (one extra get_item).

    Returns:
        {'application_id', 'owner_team_id', 'created_by'} (values may be None),
        or None when the use case does not exist.
    """
    item = _get_projected('USECASES', f'USECASE#{usecase_id}', ('application_id', 'owner_team_id'))
    if item is None:
        return None
    created_by = None
    if include_creator:
        creator = _get_projected(f'USECASE#{usecase_id}', 'CREATED_BY', ('sub',))
        created_by = (creator or {}).get('sub') or None
    return {
        'application_id': item.get('application_id') or None,
        'owner_team_id': item.get('owner_team_id') or None,
        'created_by': created_by,
    }


def get_suite_owner(suite_id: str) -> Optional[dict]:
    """
    Read the ownership fields of a test suite (TEST_SUITES/SUITE#{id}).

    Returns:
        {'application_id', 'owner_team_id'} (values may be None), or None when
        the suite does not exist.
    """
    item = _get_projected('TEST_SUITES', f'SUITE#{suite_id}', ('application_id', 'owner_team_id'))
    if item is None:
        return None
    return {
        'application_id': item.get('application_id') or None,
        'owner_team_id': item.get('owner_team_id') or None,
    }


_EXECUTION_AUTH_FIELDS = ('status', 'worker_token_hash', 'suite_id', 'suite_execution_id')


def get_execution_record(usecase_id: str, execution_id: str) -> Optional[dict]:
    """
    Read the authorization fields of a use case execution
    (USECASE_EXECUTION#{usecase_id}/EXECUTION#{execution_id}).

    The key includes the use case, so a hit also proves the execution
    belongs to that use case.

    Returns:
        {'status', 'worker_token_hash', 'suite_id', 'suite_execution_id'}
        (values may be None), or None when the execution does not exist.
    """
    item = _get_projected(f'USECASE_EXECUTION#{usecase_id}', f'EXECUTION#{execution_id}',
                          _EXECUTION_AUTH_FIELDS)
    if item is None:
        return None
    return {field: item.get(field) or None for field in _EXECUTION_AUTH_FIELDS}


def get_suite_execution_record(suite_id: str, execution_id: str) -> Optional[dict]:
    """
    Read a suite execution (SUITE_EXECUTION#{suite_id}/EXECUTION#{execution_id}).

    Returns:
        {'status'} (value may be None), or None when it does not exist.
    """
    item = _get_projected(f'SUITE_EXECUTION#{suite_id}', f'EXECUTION#{execution_id}', ('status',))
    if item is None:
        return None
    return {'status': item.get('status') or None}


def list_team_apps(team_id: str) -> list:
    """
    List all applications owned by a team.

    Uses GSI2 (team-apps-index) with gsi2pk=OWNERTEAM#{team_id}.

    Args:
        team_id: Team ID.

    Returns:
        List of application items.
    """
    table = _get_table()
    response = table.query(
        IndexName=TEAM_APPS_INDEX,
        KeyConditionExpression=Key('gsi2pk').eq(f'OWNERTEAM#{team_id}')
    )
    return response.get('Items', [])


# ---------------------------------------------------------------------------
# Shared Access Operations
# ---------------------------------------------------------------------------


def grant_shared_access(
    owner_team_id: str,
    target_team_id: str,
    app_id: str,
    level: str,
    actor: str,
) -> dict:
    """
    Grant shared access to an application for a target team.

    Implements BL-4: validates owner != target, writes share item with GSI2 projection.

    Args:
        owner_team_id: Team that owns the application.
        target_team_id: Team receiving access.
        app_id: Application ID being shared.
        level: Access level ('view', 'execute', 'full').
        actor: Sub of the user granting access.

    Returns:
        Grant record dict.

    Raises:
        ValueError: If owner_team_id == target_team_id.
    """
    if owner_team_id == target_team_id:
        raise ValueError("Cannot share an application with its own team")

    table = _get_table()
    grant_id = generate_uuid7()
    now = get_current_timestamp()

    grant_record = {
        'pk': f'TEAM#{owner_team_id}',
        'sk': f'SHARE#{target_team_id}#{app_id}',
        'grant_id': grant_id,
        'owner_team_id': owner_team_id,
        'target_team_id': target_team_id,
        'app_id': app_id,
        'level': level,
        'granted_at': now,
        'granted_by': actor,
        'gsi2pk': f'SHAREDWITH#{target_team_id}',
        'gsi2sk': f'GRANT#{grant_id}',
    }

    table.put_item(Item=grant_record)
    logger.info(
        f"Granted {level} access on app {app_id} from team {owner_team_id} to team {target_team_id}"
    )
    return grant_record


def revoke_shared_access(owner_team_id: str, target_team_id: str, app_id: str) -> None:
    """
    Revoke shared access for an application.

    Args:
        owner_team_id: Team that owns the application.
        target_team_id: Team whose access is being revoked.
        app_id: Application ID.
    """
    table = _get_table()
    table.delete_item(
        Key={'pk': f'TEAM#{owner_team_id}', 'sk': f'SHARE#{target_team_id}#{app_id}'}
    )
    logger.info(f"Revoked shared access on app {app_id} from team {target_team_id}")


def list_shared_access(team_id: str) -> list:
    """
    List all shared access grants issued BY a team (outgoing shares).

    Args:
        team_id: Team ID (the owner/grantor).

    Returns:
        List of grant dicts.
    """
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key('pk').eq(f'TEAM#{team_id}') & Key('sk').begins_with('SHARE#')
    )
    return response.get('Items', [])


def list_apps_shared_with_team(team_id: str) -> list:
    """
    List all shared access grants targeting a team (incoming shares).

    Uses GSI2 with gsi2pk=SHAREDWITH#{team_id}.

    Args:
        team_id: Team ID (the target/recipient).

    Returns:
        List of grant dicts.
    """
    table = _get_table()
    response = table.query(
        IndexName=TEAM_APPS_INDEX,
        KeyConditionExpression=Key('gsi2pk').eq(f'SHAREDWITH#{team_id}')
    )
    return response.get('Items', [])


# ---------------------------------------------------------------------------
# Test Case Override Operations
# ---------------------------------------------------------------------------


def put_testcase_override(testcase_id: str, override: dict) -> dict:
    """
    Create or update a test case visibility override.

    Args:
        testcase_id: Use case / test case ID.
        override: Dict with 'allowed_subs' (list) and/or 'allowed_roles' (list).

    Returns:
        The stored override item.
    """
    table = _get_table()
    now = get_current_timestamp()

    item = {
        'pk': f'USECASE#{testcase_id}',
        'sk': 'OVERRIDE',
        'testcase_id': testcase_id,
        'allowed_subs': override.get('allowed_subs', []),
        'allowed_roles': override.get('allowed_roles', []),
        'created_at': override.get('created_at', now),
        'created_by': override.get('created_by', ''),
    }

    table.put_item(Item=item)
    logger.info(f"Put test case override for {testcase_id}")
    return item


def get_testcase_override(testcase_id: str) -> Optional[dict]:
    """
    Get the visibility override for a test case.

    Args:
        testcase_id: Use case / test case ID.

    Returns:
        Override dict, or None if no override exists.
    """
    table = _get_table()
    response = table.get_item(
        Key={'pk': f'USECASE#{testcase_id}', 'sk': 'OVERRIDE'}
    )
    return response.get('Item')


# BatchGetItem accepts at most 100 keys per request.
_BATCH_GET_MAX_KEYS = 100
# Bound the UnprocessedKeys retry loop (throttling); callers fail closed on error.
_BATCH_GET_MAX_ATTEMPTS = 5


def batch_get_testcase_overrides(testcase_ids: list) -> dict:
    """
    Load the visibility overrides of many test cases with BatchGetItem on
    USECASE#{id}/OVERRIDE (chunks of 100 keys, UnprocessedKeys retried).

    Args:
        testcase_ids: Use case / test case IDs (duplicates ignored).

    Returns:
        {testcase_id: override item} for the test cases that have one.

    Raises:
        RuntimeError when keys are still unprocessed after the retries, or
        the underlying ClientError; callers deny on error.
    """
    unique_ids = list(dict.fromkeys(testcase_ids))
    if not unique_ids:
        return {}
    dynamodb = boto3.resource('dynamodb')
    table_name = get_table_name()
    overrides = {}
    for start in range(0, len(unique_ids), _BATCH_GET_MAX_KEYS):
        chunk = unique_ids[start:start + _BATCH_GET_MAX_KEYS]
        request_items = {table_name: {
            'Keys': [{'pk': f'USECASE#{tc}', 'sk': 'OVERRIDE'} for tc in chunk],
        }}
        for _ in range(_BATCH_GET_MAX_ATTEMPTS):
            response = dynamodb.batch_get_item(RequestItems=request_items)
            for item in response.get('Responses', {}).get(table_name, []):
                overrides[item['pk'].split('#', 1)[1]] = item
            request_items = response.get('UnprocessedKeys') or {}
            if not request_items:
                break
        if request_items:
            raise RuntimeError('batch_get_testcase_overrides: keys left unprocessed')
    return overrides

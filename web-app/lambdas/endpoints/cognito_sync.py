"""
Cognito group synchronization utilities.

Creates, deletes, and manages Cognito user pool groups that correspond to team roles.
For each team, 4 groups are created: team-{teamId}-{role} for each role in TEAM_ROLES.
Admin is studio-wide (global 'admins' group) and never a team group.

Operations:
- ensure_team_groups: Create all 4 role groups for a team (idempotent)
- delete_team_groups: Delete all 4 role groups, plus the legacy -admin group (idempotent)
- set_user_role: Change a user's role (add-first-then-remove, no access gap)
- remove_user_from_team_role: Remove a user from a specific team role group
- count_studio_admins: Count members of the global 'admins' group
- is_last_studio_admin: Last-admin guard for the global 'admins' group
"""

import logging
import boto3
from role_scopes import TEAM_ROLES

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Roles that get a Cognito group per team
_TEAM_ROLES = TEAM_ROLES

# Team groups created by older releases that must still be cleaned up on delete.
# 'team-{id}-admin' used to (wrongly) grant studio admin.
_LEGACY_TEAM_ROLES = ('admin',)

# The only group that grants studio-wide admin
ADMINS_GROUP = 'admins'


def ensure_team_groups(team_id: str, user_pool_id: str) -> list:
    """
    Ensure all 4 role groups exist for a team in the Cognito User Pool.

    Creates groups with the naming convention: team-{teamId}-{role}
    Swallows GroupExistsException if groups already exist (idempotent).

    Args:
        team_id: The team identifier.
        user_pool_id: The Cognito User Pool ID.

    Returns:
        List of group names that were created or already existed.
    """
    client = boto3.client('cognito-idp')
    group_names = []

    for role in _TEAM_ROLES:
        group_name = f'team-{team_id}-{role}'
        try:
            client.create_group(
                GroupName=group_name,
                UserPoolId=user_pool_id,
                Description=f'Team {team_id} - {role} role',
            )
            logger.info(f"Created Cognito group: {group_name}")
        except client.exceptions.GroupExistsException:
            logger.info(f"Cognito group already exists: {group_name}")
        except Exception as e:
            logger.error(f"Failed to create Cognito group {group_name}: {e}")
            raise

        group_names.append(group_name)

    return group_names


def delete_team_groups(team_id: str, user_pool_id: str) -> list:
    """
    Delete all 4 role groups for a team from the Cognito User Pool, plus the
    legacy team-{teamId}-admin group if it still exists.

    Idempotent: swallows ResourceNotFoundException if a group doesn't exist.

    Args:
        team_id: The team identifier.
        user_pool_id: The Cognito User Pool ID.

    Returns:
        List of group names that were deleted or already absent.
    """
    client = boto3.client('cognito-idp')
    group_names = []

    for role in _TEAM_ROLES + _LEGACY_TEAM_ROLES:
        group_name = f'team-{team_id}-{role}'
        try:
            client.delete_group(
                GroupName=group_name,
                UserPoolId=user_pool_id,
            )
            logger.info(f"Deleted Cognito group: {group_name}")
        except client.exceptions.ResourceNotFoundException:
            logger.info(f"Cognito group already absent: {group_name}")
        except Exception as e:
            logger.error(f"Failed to delete Cognito group {group_name}: {e}")
            raise

        group_names.append(group_name)

    return group_names


def remove_user_from_team_role(sub: str, team_id: str, role: str, user_pool_id: str) -> None:
    """
    Remove a user from a specific team role group in Cognito.

    Args:
        sub: The Cognito user sub (username).
        team_id: The team identifier.
        role: The role to remove (e.g. 'editor', 'viewer').
        user_pool_id: The Cognito User Pool ID.

    Raises:
        Exception: If the Cognito API call fails (other than user not in group).
    """
    client = boto3.client('cognito-idp')
    group_name = f'team-{team_id}-{role}'

    try:
        client.admin_remove_user_from_group(
            UserPoolId=user_pool_id,
            Username=sub,
            GroupName=group_name,
        )
        logger.info(f"Removed user {sub} from group {group_name}")
    except Exception as e:
        logger.error(f"Failed to remove user {sub} from group {group_name}: {e}")
        raise


def set_user_role(sub: str, team_id: str, old_role: str, new_role: str, user_pool_id: str) -> None:
    """
    Change a user's role in a team by updating Cognito group membership.

    Implements BL-6: add-first-then-remove ordering to prevent access gaps.
    The user is briefly in BOTH groups (more permissive, never less).

    Args:
        sub: The Cognito user sub (username).
        team_id: The team identifier.
        old_role: Current role to remove (e.g. 'viewer').
        new_role: New role to add (e.g. 'editor').
        user_pool_id: The Cognito User Pool ID.

    Raises:
        Exception: If adding the new group fails.
    """
    client = boto3.client('cognito-idp')
    new_group_name = f'team-{team_id}-{new_role}'
    old_group_name = f'team-{team_id}-{old_role}'

    # Step 1: Add to new group FIRST (no access gap)
    try:
        client.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=sub,
            GroupName=new_group_name,
        )
        logger.info(f"Added user {sub} to group {new_group_name}")
    except Exception as e:
        logger.error(f"Failed to add user {sub} to group {new_group_name}: {e}")
        raise

    # Step 2: Remove from old group (safe — user already has new group)
    try:
        client.admin_remove_user_from_group(
            UserPoolId=user_pool_id,
            Username=sub,
            GroupName=old_group_name,
        )
        logger.info(f"Removed user {sub} from group {old_group_name}")
    except Exception as e:
        # Log warning but don't raise — user has both groups briefly (more permissive, not less)
        logger.warning(
            f"Failed to remove user {sub} from old group {old_group_name}: {e}. "
            f"User may have both roles briefly."
        )


def count_studio_admins(user_pool_id: str) -> int:
    """
    Count the members of the global 'admins' group (the only studio admins).

    Paginates list_users_in_group. Used by the last-admin guard.

    Args:
        user_pool_id: The Cognito User Pool ID.

    Returns:
        Number of users in the 'admins' group.
    """
    client = boto3.client('cognito-idp')
    count = 0
    kwargs = {'UserPoolId': user_pool_id, 'GroupName': ADMINS_GROUP}
    while True:
        response = client.list_users_in_group(**kwargs)
        count += len(response.get('Users', []))
        next_token = response.get('NextToken')
        if not next_token:
            return count
        kwargs['NextToken'] = next_token


def is_last_studio_admin(username: str, user_pool_id: str) -> bool:
    """
    Last-admin guard: True if `username` is in 'admins' and is its only member.

    Errors propagate so callers fail closed (refuse the change).

    Args:
        username: Cognito username (sub) of the user being demoted or deleted.
        user_pool_id: The Cognito User Pool ID.

    Returns:
        True when removing this user would leave the studio without an admin.
    """
    client = boto3.client('cognito-idp')
    kwargs = {'UserPoolId': user_pool_id, 'Username': username}
    while True:
        response = client.admin_list_groups_for_user(**kwargs)
        if any(g.get('GroupName') == ADMINS_GROUP for g in response.get('Groups', [])):
            return count_studio_admins(user_pool_id) <= 1
        next_token = response.get('NextToken')
        if not next_token:
            return False
        kwargs['NextToken'] = next_token

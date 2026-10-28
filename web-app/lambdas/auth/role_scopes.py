"""
Single source of truth for role-to-scope mappings.

Defines 5 roles: admin, team_lead, editor, executor, viewer.
Provides functions for resolving scopes from Cognito group names.

Admin is studio-wide and lives only in the global 'admins' group. It is never
a team role: 'team-{teamId}-admin' is not a recognized group and grants nothing.

Group naming convention:
- Legacy groups: 'users', 'admins'
- Team groups: 'team-{teamId}-{role}' with role in TEAM_ROLES (e.g. team-abc123-editor)
"""

import re
from typing import Optional

# Ordered roles — highest privilege first
ROLES = ['admin', 'team_lead', 'editor', 'executor', 'viewer']

# Roles that can be held inside a team (admin is studio-wide only)
TEAM_ROLES = ('team_lead', 'editor', 'executor', 'viewer')

# M2M (OAuth client) rules: a client is bound to one team with at most the
# 'editor' role and may never hold studio-wide or team-management scopes.
M2M_TEAM_ROLES = ('editor', 'executor', 'viewer')
M2M_FORBIDDEN_SCOPES = frozenset({'api/admin', 'api/teams.manage'})

# Numeric rank for role comparison (higher = more privilege)
ROLE_RANK = {
    'admin': 5,
    'team_lead': 4,
    'editor': 3,
    'executor': 2,
    'viewer': 1,
}

# Access level rank for shared resources (higher = more access)
ACCESS_RANK = {
    'full': 4,
    'edit': 3,
    'execute': 2,
    'view': 1,
}

# Base scopes all authenticated users receive
_BASE_SCOPES = [
    'api/usecases.read',
    'api/templates.read',
    'api/executions.read',
    'api/suite.read',
    'api/applications.read',
]

# Scopes by role — each role gets its own scopes PLUS all scopes from roles below it
_ROLE_SCOPES = {
    'viewer': [
        'api/usecases.read',
        'api/templates.read',
        'api/executions.read',
        'api/suite.read',
        'api/applications.read',
    ],
    'executor': [
        'api/usecases.execute',
        'api/executions.write',
    ],
    'editor': [
        'api/usecases.write',
        'api/templates.write',
        'api/suite.write',
        'api/applications.write',
        'api/oauth-clients.read',
        'api/oauth-clients.write',
    ],
    'team_lead': [
        'api/teams.manage',
    ],
    'admin': [
        'api/admin',
    ],
}

# Precomputed cumulative scopes per role (role + all roles below)
_CUMULATIVE_SCOPES = {}
for i, role in enumerate(reversed(ROLES)):
    # Start from least privilege and accumulate
    if i == 0:
        _CUMULATIVE_SCOPES[role] = set(_ROLE_SCOPES[role])
    else:
        prev_role = list(reversed(ROLES))[i - 1]
        _CUMULATIVE_SCOPES[role] = set(_ROLE_SCOPES[role]) | _CUMULATIVE_SCOPES[prev_role]

# Legacy group mappings (backward compatible with existing 'users' and 'admins' groups)
_LEGACY_GROUP_MAPPINGS = {
    'users': 'editor',
    'admins': 'admin',
}

# Regex for team group names: team-{teamId}-{role}
_TEAM_GROUP_RE = re.compile(r'^team-([a-zA-Z0-9_-]+)-([a-z_]+)$')


def scopes_for_role(role: str) -> set:
    """
    Return the full set of scopes for a given role.

    The returned set includes all scopes the role inherits from lower roles.

    Args:
        role: One of 'admin', 'team_lead', 'editor', 'executor', 'viewer'

    Returns:
        Set of scope strings. Empty set if role is not recognized.
    """
    return set(_CUMULATIVE_SCOPES.get(role, set()))


def parse_group(group_name: str) -> Optional[dict]:
    """
    Parse a Cognito group name into its components.

    Handles both legacy groups ('users', 'admins') and team groups
    ('team-{teamId}-{role}').

    Args:
        group_name: Raw Cognito group name

    Returns:
        Dict with keys: 'team_id' (str or None), 'role' (str), 'group_name' (str)
        Returns None if the group name is not recognized.
    """
    group_name = group_name.strip()

    # Check legacy groups
    if group_name in _LEGACY_GROUP_MAPPINGS:
        return {
            'team_id': None,
            'role': _LEGACY_GROUP_MAPPINGS[group_name],
            'group_name': group_name,
        }

    # Check team group pattern
    match = _TEAM_GROUP_RE.match(group_name)
    if match:
        team_id = match.group(1)
        role = match.group(2)
        if role in TEAM_ROLES:
            return {
                'team_id': team_id,
                'role': role,
                'group_name': group_name,
            }

    return None


def is_admin_group(group_name: str) -> bool:
    """
    Check if a group name grants admin privileges.

    Only the global 'admins' group does. Team groups never grant admin.

    Args:
        group_name: Raw Cognito group name

    Returns:
        True if the group is the global 'admins' group.
    """
    return group_name.strip() == 'admins'


def scopes_for_groups(groups: list) -> set:
    """
    Resolve the union of all scopes from a list of Cognito group names.

    Handles both legacy groups and team-role groups. Unknown groups are
    silently skipped (fail-open for scope resolution, not for auth decisions).

    Args:
        groups: List of Cognito group names from the cognito:groups claim.

    Returns:
        Set of scope strings derived from all recognized group memberships.
    """
    scopes = set()
    for group in groups:
        group_name = group.strip() if isinstance(group, str) else str(group)
        parsed = parse_group(group_name)
        if parsed:
            scopes.update(scopes_for_role(parsed['role']))
    return scopes

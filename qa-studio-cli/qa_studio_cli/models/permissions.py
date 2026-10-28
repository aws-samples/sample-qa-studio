"""Pydantic models for the permissions / team-management domain."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class Team(BaseModel):
    """A team that owns applications and has members with roles."""

    id: str
    name: str
    description: Optional[str] = None
    member_count: int = 0
    application_count: int = 0


class Member(BaseModel):
    """A member within a team, with an assigned role."""

    user_id: str
    email: str
    role: str
    joined_at: Optional[datetime] = None


class SharedAccessGrant(BaseModel):
    """A grant of shared access to an application for another team."""

    grant_id: str
    target_team_id: str
    target_team_name: str
    access_level: str  # view, execute, full
    granted_at: Optional[datetime] = None


class UserWithTeams(BaseModel):
    """A platform user with their team memberships."""

    user_id: str
    email: str
    teams: List[dict] = []  # [{team_id, name, role}]

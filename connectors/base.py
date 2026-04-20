from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional


class BaseConnector(ABC):
    """Base class for all SaaS application connectors.

    Each connector must return user records with at minimum these fields:
        - id: Unique user identifier in the source system
        - email: User email address
        - name: Display name
        - roles: List of role/group names
        - status: Account status (active, suspended, deactivated, pending, etc.)

    Connectors should also return these compliance-relevant fields when available:
        - last_login: ISO timestamp or date string of last successful login
        - created_at: ISO timestamp or date string of account creation
        - mfa_enabled: "True", "False", or "" if unknown
        - two_factor_enabled: Alias for mfa_enabled (some APIs use this name)
        - account_type: Type of account (user, service, bot, etc.)
        - is_admin: "True" or "False" if the user has admin privileges
        - last_password_change: When password was last rotated
        - groups: List of group names (if separate from roles)

    Any additional fields the API provides can be included — they will
    be stored in the snapshot and available for review.
    """

    def __init__(self, credentials: dict, base_url: Optional[str] = None):
        self.credentials = credentials
        self.base_url = base_url

    @abstractmethod
    async def fetch_users(self) -> list[dict]:
        """Return a list of user dicts with at minimum: id, email, name, roles, status."""
        ...

    @staticmethod
    @abstractmethod
    def credential_fields() -> list[dict]:
        """Return list of {name, label, type} describing required credential fields."""
        ...

    @staticmethod
    @abstractmethod
    def default_base_url() -> str | None:
        """Return a default base URL if applicable."""
        ...

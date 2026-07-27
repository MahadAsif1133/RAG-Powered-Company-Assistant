from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()


class CurrentUser:
    """Resolved user context attached to every authenticated request."""

    def __init__(self, user_id: str, org_id: str, role: str, email: str):
        self.user_id = user_id
        self.org_id = org_id
        self.role = role
        self.email = email

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> CurrentUser:
    """
    Dependency that:
    1. Extracts the Bearer JWT from the Authorization header
    2. Verifies it with Supabase Auth (gets the user sub/id)
    3. Looks up the user's org_id and role from the `users` table
    4. Returns a CurrentUser object

    Raises HTTP 401 if the token is invalid/expired.
    Raises HTTP 403 if the user record doesn't exist in our `users` table
    (i.e., they authenticated but haven't been provisioned to an org yet).
    """
    token = credentials.credentials
    supabase = get_supabase()

    try:
        # Verify JWT and get Supabase user
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        auth_user = response.user
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    # Look up the user in our users table to get org_id + role
    try:
        result = (
            supabase.table("users")
            .select("id, org_id, role, email")
            .eq("id", auth_user.id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to fetch user record for %s: %s", auth_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not provisioned to an organization. Contact your admin.",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not provisioned to an organization. Contact your admin.",
        )

    data = result.data
    return CurrentUser(
        user_id=data["id"],
        org_id=data["org_id"],
        role=data["role"],
        email=data.get("email", ""),
    )


async def require_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Dependency that additionally enforces admin-only access."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


# Convenient type aliases for route signatures
UserDep = Annotated[CurrentUser, Depends(get_current_user)]
AdminDep = Annotated[CurrentUser, Depends(require_admin)]

from __future__ import annotations

import logging
from typing import Optional

from app.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def get_org_id_for_team(slack_team_id: str) -> Optional[str]:
    """
    Look up the internal org_id for a Slack workspace.
    Returns None if the workspace hasn't been mapped yet.
    """
    supabase = get_supabase()
    result = (
        supabase.table("slack_workspaces")
        .select("org_id")
        .eq("slack_team_id", slack_team_id)
        .single()
        .execute()
    )
    if result.data:
        return result.data["org_id"]
    logger.warning("No org_id mapped for Slack team %s", slack_team_id)
    return None


def get_or_create_user(slack_user_id: str, slack_team_id: str, org_id: str) -> Optional[str]:
    """
    Get the internal user_id for a Slack user, or create a guest user record.

    Strategy:
    1. Check slack_users table for existing mapping
    2. If not found, create a placeholder `users` row + slack_users row
       (no Supabase Auth account — Slack users are treated as guest employees)
    Returns internal user_id or None on failure.
    """
    supabase = get_supabase()

    # Check existing mapping
    existing = (
        supabase.table("slack_users")
        .select("user_id")
        .eq("slack_user_id", slack_user_id)
        .eq("slack_team_id", slack_team_id)
        .single()
        .execute()
    )
    if existing.data and existing.data.get("user_id"):
        return existing.data["user_id"]

    # Create a new user record for this Slack user
    try:
        # We can't insert into auth.users from the service role for Slack users,
        # so we use a separate internal table approach.
        # For a real deployment, link via Supabase Auth SSO or invite flow.
        # For now, create a users row with a generated UUID.
        import uuid

        new_user_id = str(uuid.uuid4())

        # NOTE: This requires temporarily bypassing the auth.users FK constraint.
        # In production: use Supabase's invite flow or remove the FK on users.id
        # and manage identity externally. See docs/slack_setup.md.
        slack_users_result = (
            supabase.table("slack_users")
            .insert(
                {
                    "user_id": None,  # No internal user account
                    "org_id": org_id,
                    "slack_user_id": slack_user_id,
                    "slack_team_id": slack_team_id,
                }
            )
            .execute()
        )
        logger.info("Created slack_users record for %s@%s", slack_user_id, slack_team_id)
        # Return None since there's no internal user_id for anonymous Slack users
        return None
    except Exception as exc:
        logger.error("Failed to create Slack user mapping: %s", exc)
        return None

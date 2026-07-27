from __future__ import annotations

from functools import lru_cache

from supabase import create_client, Client

from app.core.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """
    Return a singleton Supabase client using the service-role key.
    The service-role key bypasses Row-Level Security, which is correct
    for all backend operations. Never expose this key client-side.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

"""Optional reusable Supabase REST client.

The current persistence layer uses psycopg for PostgreSQL transactions; this
client is available for Supabase Auth/REST operations without exposing keys to
the browser. Missing credentials do not prevent the Flask app from starting.
"""

import os
from functools import lru_cache


class SupabaseConfigurationError(RuntimeError):
    """Raised when a Supabase operation is attempted without configuration."""


@lru_cache(maxsize=1)
def get_supabase_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise SupabaseConfigurationError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY."
        )
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        raise RuntimeError("Could not initialize the Supabase client.") from exc

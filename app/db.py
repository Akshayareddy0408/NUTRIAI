import os
import psycopg
from psycopg.rows import dict_row

def get_db_connection():
    # Supabase exposes a standard PostgreSQL connection string. Keep supporting
    # existing deployments while allowing the Supabase-specific env name.
    database_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "Supabase database is not configured. Set SUPABASE_DB_URL "
            "(or the legacy DATABASE_URL) in your environment."
        )

    return psycopg.connect(
        database_url,
        row_factory=dict_row
    )


from werkzeug.security import generate_password_hash, check_password_hash
from psycopg.errors import UniqueViolation
from app.db import get_db_connection


def create_user(email, password):
    email = email.strip().lower()

    if not email or "@" not in email or "." not in email.split("@", 1)[-1]:
        return False, "Enter a valid email address."

    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO public.app_users (email, password_hash)
                VALUES (%s, %s)
                """,
                (email, password_hash)
            )
        return True, "Account created successfully. You can now log in."

    except UniqueViolation:
        return False, "An account with this email already exists."


def authenticate(email, password):
    email = email.strip().lower()

    with get_db_connection() as conn:
        user = conn.execute(
            """
            SELECT password_hash
            FROM public.app_users
            WHERE email = %s
            """,
            (email,)
        ).fetchone()

    return bool(
        user and check_password_hash(user["password_hash"], password)
    )

"""HTTP Basic authentication and role-based API access."""

import secrets
from typing import Annotated, Callable

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import text
from app.db.repositories import get_engine
from app.security.audit import record_audit

security = HTTPBasic(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Basic"},
        )

    with get_engine().connect() as connection:
        user = connection.execute(
            text(
                """
                SELECT id::text AS id, username, password_hash, role, is_active
                FROM app_users
                WHERE username = :username
                """
            ),
            {"username": credentials.username},
        ).mappings().one_or_none()

    valid_password = False
    if user is not None:
        try:
            valid_password = bcrypt.checkpw(
                credentials.password.encode("utf-8"),
                user["password_hash"].encode("utf-8"),
            )
        except ValueError:
            valid_password = False

    if (
        user is None
        or not valid_password
        or not user["is_active"]
        or not secrets.compare_digest(user["username"], credentials.username)
    ):
        with get_engine().begin() as connection:
            record_audit(
                connection,
                action="login_failure",
                outcome="denied",
                summary={},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Basic"},
        )

    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
    }


def require_roles(*roles: str) -> Callable:
    def dependency(
        user: Annotated[dict[str, str], Depends(get_current_user)],
    ) -> dict[str, str]:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to perform this action.",
            )
        return user

    return dependency


AuthenticatedUser = Annotated[dict[str, str], Depends(get_current_user)]
AdminUser = Annotated[dict[str, str], Depends(require_roles("admin"))]
AnalystUser = Annotated[
    dict[str, str], Depends(require_roles("admin", "analyst"))
]

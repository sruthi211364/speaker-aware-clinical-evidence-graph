"""Prototype bearer-token auth stub.

This is intentionally minimal: a single shared token checked against
Authorization: Bearer <token>. It exists so every patient-data-bearing
endpoint already depends on an auth check and can be swapped for real
per-user RBAC (see SECURITY.md) without touching route signatures.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    settings = get_settings()
    if credentials is None or credentials.credentials != settings.api_bearer_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )
    return credentials.credentials

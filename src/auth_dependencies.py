"""FastAPI authentication dependencies and ownership checks."""

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth import AuthError, AuthIdentity, AuthService


bearer_scheme = HTTPBearer(auto_error=False)
auth_service = AuthService()


def _as_http_error(error: AuthError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


def current_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."},
        )
    try:
        return auth_service.authenticate(credentials.credentials)
    except AuthError as error:
        raise _as_http_error(error) from error


def optional_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthIdentity]:
    if credentials is None:
        return None
    return current_identity(credentials)


def require_owner(identity: AuthIdentity, user_id: str) -> None:
    if identity.user_id != user_id and identity.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "You cannot access another learner's records.",
            },
        )

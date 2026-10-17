"""Password authentication and opaque bearer-session management."""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from src.config import Config
from src.database import AuthRepository


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AuthIdentity:
    user_id: str
    role: str
    session_id: str
    expires_at: datetime


class PasswordHasher:
    def __init__(self, iterations: Optional[int] = None):
        self.iterations = iterations or Config.PASSWORD_PBKDF2_ITERATIONS

    @staticmethod
    def validate(password: str) -> None:
        if len(password) < 10 or len(password) > 128:
            raise AuthError(
                "WEAK_PASSWORD",
                "Password must contain between 10 and 128 characters.",
            )
        categories = sum(
            (
                any(char.islower() for char in password),
                any(char.isupper() for char in password),
                any(char.isdigit() for char in password),
                any(not char.isalnum() for char in password),
            )
        )
        if categories < 3:
            raise AuthError(
                "WEAK_PASSWORD",
                "Password must use at least three character categories.",
            )

    def hash(self, password: str) -> tuple[str, str, int]:
        self.validate(password)
        salt = secrets.token_bytes(16)
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, self.iterations
        )
        return (
            base64.b64encode(derived).decode("ascii"),
            base64.b64encode(salt).decode("ascii"),
            self.iterations,
        )

    @staticmethod
    def verify(password: str, encoded_hash: str, encoded_salt: str, iterations: int) -> bool:
        try:
            expected = base64.b64decode(encoded_hash)
            salt = base64.b64decode(encoded_salt)
        except (ValueError, TypeError):
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)


class AuthService:
    def __init__(
        self,
        repository: Optional[AuthRepository] = None,
        hasher: Optional[PasswordHasher] = None,
    ):
        self.repository = repository or AuthRepository()
        self.hasher = hasher or PasswordHasher()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def register(self, user_id: str, password: str) -> tuple[str, AuthIdentity]:
        password_hash, salt, iterations = self.hasher.hash(password)
        status = self.repository.create_user(
            user_id=user_id,
            password_hash=password_hash,
            password_salt=salt,
            password_iterations=iterations,
        )
        if status == "exists":
            raise AuthError("USER_EXISTS", "This user ID is already registered.", 409)
        if status == "legacy":
            raise AuthError(
                "LEGACY_ACCOUNT_REQUIRES_PASSWORD",
                "This migrated account needs a password set with manage_user.py.",
                409,
            )
        return self._issue_session(user_id, "student")

    def login(self, user_id: str, password: str) -> tuple[str, AuthIdentity]:
        credentials = self.repository.get_credentials(user_id)
        invalid = AuthError(
            "INVALID_CREDENTIALS", "User ID or password is incorrect.", 401
        )
        if not credentials or not credentials.get("is_active"):
            raise invalid
        if not credentials.get("password_hash"):
            raise AuthError(
                "LEGACY_ACCOUNT_REQUIRES_PASSWORD",
                "This migrated account needs a password set with manage_user.py.",
                409,
            )
        if not self.hasher.verify(
            password,
            credentials["password_hash"],
            credentials["password_salt"],
            credentials["password_iterations"],
        ):
            raise invalid
        return self._issue_session(user_id, str(credentials.get("role", "student")))

    def _issue_session(self, user_id: str, role: str) -> tuple[str, AuthIdentity]:
        raw_token = secrets.token_urlsafe(32)
        session_id = f"sess_{uuid4().hex}"
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=Config.AUTH_SESSION_HOURS
        )
        self.repository.create_session(
            session_id=session_id,
            user_id=user_id,
            token_hash=self._token_hash(raw_token),
            expires_at=expires_at,
        )
        return raw_token, AuthIdentity(user_id, role, session_id, expires_at)

    def authenticate(self, token: str) -> AuthIdentity:
        record = self.repository.resolve_session(self._token_hash(token))
        if not record:
            raise AuthError("INVALID_SESSION", "Authentication is required.", 401)
        return AuthIdentity(**record)

    def logout(self, token: str) -> None:
        self.repository.revoke_session(self._token_hash(token))

    def set_password(self, user_id: str, password: str) -> None:
        password_hash, salt, iterations = self.hasher.hash(password)
        if not self.repository.set_password(user_id, password_hash, salt, iterations):
            raise AuthError("USER_NOT_FOUND", "User does not exist.", 404)

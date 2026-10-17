import pytest
from sqlalchemy import create_engine, inspect, text

from src.auth import AuthError, AuthService, PasswordHasher
from src.database import AuthRepository, Database, UserRepository


def make_auth(tmp_path):
    database = Database(f"sqlite:///{(tmp_path / 'auth.db').as_posix()}")
    service = AuthService(
        AuthRepository(database), PasswordHasher(iterations=1_000)
    )
    return database, service


def test_register_login_authenticate_and_revoke(tmp_path):
    database, service = make_auth(tmp_path)
    token, identity = service.register("secure_student", "StrongPass!123")
    assert identity.user_id == "secure_student"
    assert service.authenticate(token).session_id == identity.session_id

    second_token, second_identity = service.login(
        "secure_student", "StrongPass!123"
    )
    assert second_identity.user_id == "secure_student"
    service.logout(second_token)
    with pytest.raises(AuthError) as error:
        service.authenticate(second_token)
    assert error.value.code == "INVALID_SESSION"
    assert UserRepository(database).count() == 1


def test_password_policy_and_generic_invalid_credentials(tmp_path):
    _, service = make_auth(tmp_path)
    with pytest.raises(AuthError) as weak:
        service.register("student", "password")
    assert weak.value.code == "WEAK_PASSWORD"

    service.register("student", "StrongPass!123")
    with pytest.raises(AuthError) as invalid:
        service.login("student", "WrongPass!123")
    assert invalid.value.code == "INVALID_CREDENTIALS"


def test_legacy_user_requires_explicit_password_claim(tmp_path):
    database, service = make_auth(tmp_path)
    UserRepository(database).load_or_create("legacy_user", ["Derivatives"])
    with pytest.raises(AuthError) as error:
        service.login("legacy_user", "StrongPass!123")
    assert error.value.code == "LEGACY_ACCOUNT_REQUIRES_PASSWORD"

    service.set_password("legacy_user", "StrongPass!123")
    token, _ = service.login("legacy_user", "StrongPass!123")
    assert service.authenticate(token).user_id == "legacy_user"


def test_schema_v2_upgrades_existing_sqlite_user_table(tmp_path):
    database_path = tmp_path / "legacy.db"
    url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "user_id VARCHAR(80) PRIMARY KEY, joined_at DATETIME NOT NULL, "
                "total_minutes FLOAT NOT NULL, dataset_version VARCHAR(40) NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
        )
    engine.dispose()

    database = Database(url)
    columns = {column["name"] for column in inspect(database.engine).get_columns("users")}
    assert {
        "password_hash",
        "password_salt",
        "password_iterations",
        "role",
        "is_active",
    }.issubset(columns)
    assert "auth_sessions" in inspect(database.engine).get_table_names()

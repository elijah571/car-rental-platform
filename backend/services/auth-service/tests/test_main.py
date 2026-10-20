
from importlib import import_module

from fastapi.testclient import TestClient

from app.core.database import get_optional_db
from app.main import app
from app.services import cognito


main_module = import_module("app.main")
app.dependency_overrides[get_optional_db] = lambda: None
client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Car Rental Auth Service is running"
    }


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "auth-service",
    }


def test_readiness_without_database(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: type("Settings", (), {"database_configured": False})(),
    )

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "auth-service",
        "database": "not_configured",
    }


def test_readiness_reports_database_failure(monkeypatch):
    class FailedConnection:
        async def __aenter__(self):
            raise OSError("database unavailable")

        async def __aexit__(self, *_):
            return False

    class FailedEngine:
        def connect(self):
            return FailedConnection()

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: type("Settings", (), {"database_configured": True})(),
    )
    monkeypatch.setattr(main_module, "get_engine", lambda: FailedEngine())

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "auth-service",
        "database": "unavailable",
    }


def test_authentication_endpoints(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cognito,
        "sign_up",
        lambda *args: calls.append(("sign_up", args))
        or {"CodeDeliveryDetails": {"Destination": "a***@example.com"}},
    )
    monkeypatch.setattr(cognito, "confirm_sign_up", lambda *args: calls.append(("confirm", args)))
    monkeypatch.setattr(cognito, "resend_code", lambda *args: calls.append(("resend", args)))
    monkeypatch.setattr(cognito, "login", lambda *args: {"AccessToken": "access", "RefreshToken": "refresh"})
    monkeypatch.setattr(
        cognito,
        "refresh",
        lambda *args: calls.append(("refresh", args)) or {"AccessToken": "new-access"},
    )
    monkeypatch.setattr(cognito, "logout", lambda *args: calls.append(("logout", args)))

    response = client.post(
        "/auth/register",
        json={"email": "renter@example.com", "password": "SecurePass123!", "name": "Renter"},
    )
    assert response.status_code == 201
    assert "a***@example.com" in response.json()["message"]

    response = client.post(
        "/auth/confirm",
        json={"email": "renter@example.com", "confirmation_code": "123456"},
    )
    assert response.status_code == 200

    response = client.post("/auth/resend-code", json={"email": "renter@example.com"})
    assert response.status_code == 200

    response = client.post(
        "/auth/login",
        json={"email": "renter@example.com", "password": "SecurePass123!"},
    )
    assert response.status_code == 200
    assert response.json()["tokens"]["AccessToken"] == "access"

    response = client.post(
        "/auth/refresh",
        json={"email": "renter@example.com", "refresh_token": "opaque-refresh-token"},
    )
    assert response.status_code == 200
    assert calls[-1] == ("refresh", ("renter@example.com", "opaque-refresh-token"))

    response = client.post("/auth/logout", json={"access_token": "access"})
    assert response.status_code == 200
    assert [call[0] for call in calls] == ["sign_up", "confirm", "resend", "refresh", "logout"]


def test_authentication_request_validation():
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "short", "name": ""},
    )
    assert response.status_code == 422


def test_auth_endpoints_report_missing_cognito_configuration(monkeypatch):
    monkeypatch.setattr(cognito, "get_settings", lambda: type("Settings", (), {
        "cognito_user_pool_id": None,
        "cognito_client_id": None,
        "cognito_client_secret": None,
    })())

    response = client.post(
        "/auth/login",
        json={"email": "renter@example.com", "password": "SecurePass123!"},
    )
    assert response.status_code == 503

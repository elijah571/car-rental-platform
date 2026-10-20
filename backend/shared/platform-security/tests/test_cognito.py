from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_security.cognito import _decode_access_token


@pytest.fixture
def token_verifier(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    issuer = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_pool"

    class FakeJwkClient:
        def get_signing_key_from_jwt(self, _token):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr("platform_security.cognito._jwk_client", lambda _: FakeJwkClient())

    def issue(**overrides):
        now = datetime.now(UTC)
        claims = {
            "iss": issuer,
            "sub": "f9d7f472-86e0-4f41-9d86-64e5774a45b2",
            "token_use": "access",
            "client_id": "expected-client",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "scope": "openid email",
            "cognito:groups": ["platform-admin"],
        }
        claims.update(overrides)
        return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})

    return issue


def decode(token):
    return _decode_access_token(
        token,
        region="us-east-1",
        user_pool_id="us-east-1_pool",
        client_id="expected-client",
    )


def test_valid_signed_access_token_yields_identity(token_verifier):
    identity = decode(token_verifier())
    assert identity.subject == "f9d7f472-86e0-4f41-9d86-64e5774a45b2"
    assert identity.groups == frozenset({"platform-admin"})
    assert identity.scopes == frozenset({"openid", "email"})


def test_wrong_app_client_is_rejected(token_verifier):
    with pytest.raises(jwt.InvalidTokenError, match="different app client"):
        decode(token_verifier(client_id="another-client"))


def test_id_token_is_rejected(token_verifier):
    with pytest.raises(jwt.InvalidTokenError, match="access token"):
        decode(token_verifier(token_use="id"))


def test_expired_token_is_rejected(token_verifier):
    expired = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    with pytest.raises(jwt.ExpiredSignatureError):
        decode(token_verifier(exp=expired))

import asyncio
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient, PyJWKClientError


@dataclass(frozen=True, slots=True)
class CognitoIdentity:
    subject: str
    client_id: str
    groups: frozenset[str]
    scopes: frozenset[str]


@lru_cache(maxsize=32)
def _jwk_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)


def _decode_access_token(
    token: str,
    *,
    region: str,
    user_pool_id: str,
    client_id: str,
) -> CognitoIdentity:
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
    signing_key = _jwk_client(issuer).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False, "require": ["exp", "iat", "sub", "token_use", "client_id"]},
    )
    if claims.get("token_use") != "access":
        raise jwt.InvalidTokenError("Expected a Cognito access token")
    if claims.get("client_id") != client_id:
        raise jwt.InvalidTokenError("Token was issued to a different app client")
    groups = claims.get("cognito:groups", [])
    scope = claims.get("scope", "")
    if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
        raise jwt.InvalidTokenError("Invalid Cognito groups claim")
    return CognitoIdentity(
        subject=claims["sub"],
        client_id=claims["client_id"],
        groups=frozenset(groups),
        scopes=frozenset(scope.split()) if isinstance(scope, str) else frozenset(),
    )


async def verify_access_token(
    token: str,
    *,
    region: str,
    user_pool_id: str,
    client_id: str,
) -> CognitoIdentity:
    try:
        return await asyncio.to_thread(
            _decode_access_token,
            token,
            region=region,
            user_pool_id=user_pool_id,
            client_id=client_id,
        )
    except PyJWKClientError as exc:
        raise RuntimeError("Cognito signing keys are unavailable") from exc

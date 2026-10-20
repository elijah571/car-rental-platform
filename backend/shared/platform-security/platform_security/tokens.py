from dataclasses import dataclass

import jwt


@dataclass(frozen=True, slots=True)
class PlatformIdentity:
    subject: str
    client_id: str
    groups: frozenset[str]
    scopes: frozenset[str]


def verify_platform_token(token: str, secret: str) -> PlatformIdentity:
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="car-rental-auth",
        audience="car-rental-platform",
        options={"require": ["exp", "iat", "sub", "type", "role"]},
    )
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("Expected a platform access token")
    groups = claims.get("groups", [])
    if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
        raise jwt.InvalidTokenError("Invalid groups claim")
    return PlatformIdentity(
        subject=claims["sub"],
        client_id="car-rental-platform",
        groups=frozenset(groups),
        scopes=frozenset(),
    )

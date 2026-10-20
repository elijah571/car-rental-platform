import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from platform_security import PlatformIdentity, verify_platform_token

bearer_scheme = HTTPBearer(auto_error=False)


async def _identity_from_credentials(credentials: HTTPAuthorizationCredentials) -> PlatformIdentity:
    try:
        return verify_platform_token(credentials.credentials, get_settings().jwt_secret.get_secret_value())
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token.", headers={"WWW-Authenticate": "Bearer"}) from exc


async def optional_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> PlatformIdentity | None:
    return await _identity_from_credentials(credentials) if credentials else None


async def current_identity(
    identity: PlatformIdentity | None = Depends(optional_identity),
) -> PlatformIdentity:
    if identity is None:
        raise HTTPException(status_code=401, detail="Bearer access token required.", headers={"WWW-Authenticate": "Bearer"})
    return identity


async def require_platform_admin(
    identity: PlatformIdentity = Depends(current_identity),
) -> PlatformIdentity:
    if "platform-admin" not in identity.groups:
        raise HTTPException(status_code=403, detail="Platform administrator access is required.")
    return identity

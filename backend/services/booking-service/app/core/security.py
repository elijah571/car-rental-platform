import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from platform_security import PlatformIdentity, verify_platform_token

bearer_scheme = HTTPBearer(auto_error=False)


async def current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> PlatformIdentity:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bearer access token required.", headers={"WWW-Authenticate": "Bearer"})
    try:
        return verify_platform_token(credentials.credentials, get_settings().jwt_secret.get_secret_value())
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token.", headers={"WWW-Authenticate": "Bearer"}) from exc


async def require_platform_admin(
    identity: PlatformIdentity = Depends(current_identity),
) -> PlatformIdentity:
    if "platform-admin" not in identity.groups:
        raise HTTPException(status_code=403, detail="Platform administrator access is required.")
    return identity

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.redis import RedisError
from app.models import User


def _duration(value: str) -> int:
    match = re.fullmatch(r"(\d+)([smhd])", value.strip().lower())
    if not match:
        raise ValueError("JWT expiration must be a duration such as 50m or 7d.")
    amount, unit = int(match.group(1)), match.group(2)
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _code_digest(email: str, code: str, purpose: str = "verify") -> str:
    secret = get_settings().jwt_refresh_secret.get_secret_value().encode()
    return hmac.new(secret, f"{purpose}:{email}:{code}".encode(), hashlib.sha256).hexdigest()


async def issue_verification_code(email: str, redis) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    await redis.set(f"auth:verify:{email}", _code_digest(email, code), ex=600)
    await redis.delete(f"auth:verify-attempts:{email}")
    return code


async def verify_code(email: str, code: str, redis) -> bool:
    stored = await redis.get(f"auth:verify:{email}")
    return bool(stored and hmac.compare_digest(stored, _code_digest(email, code)))


async def issue_reset_code(email: str, redis) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    await redis.set(f"auth:password-reset:{email}", _code_digest(email, code, "reset"), ex=900)
    await redis.delete(f"auth:password-reset-attempts:{email}")
    return code


async def verify_reset_code(email: str, code: str, redis) -> bool:
    stored = await redis.get(f"auth:password-reset:{email}")
    return bool(stored and hmac.compare_digest(stored, _code_digest(email, code, "reset")))


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    secret = settings.jwt_secret.get_secret_value()
    if len(secret) < 32 or "replace_with" in secret.lower():
        raise HTTPException(status_code=503, detail="JWT_SECRET must contain at least 32 characters.")
    claims = {
        "sub": str(user.id), "email": user.email, "role": user.role,
        "groups": ["platform-admin"] if user.role == "platform-admin" else [],
        "iss": "car-rental-auth", "aud": "car-rental-platform", "type": "access",
        "iat": now, "exp": now + timedelta(seconds=_duration(settings.jwt_access_expire)),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


async def issue_refresh_token(user: User, redis) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    refresh_secret = settings.jwt_refresh_secret.get_secret_value()
    if len(refresh_secret) < 32 or "replace_with" in refresh_secret.lower():
        raise HTTPException(status_code=503, detail="JWT_REFRESH_SECRET must contain at least 32 characters.")
    key = hashlib.sha256(token.encode()).hexdigest()
    await redis.set(f"auth:refresh:{key}", str(user.id), ex=_duration(settings.jwt_refresh_expire))
    await redis.sadd(f"auth:refresh-index:{user.id}", key)
    return token


async def consume_refresh_token(token: str, redis) -> UUID | None:
    key = hashlib.sha256(token.encode()).hexdigest()
    redis_key = f"auth:refresh:{key}"
    subject = await redis.getdel(redis_key)
    if subject:
        await redis.srem(f"auth:refresh-index:{subject}", key)
        try:
            return UUID(subject)
        except ValueError:
            return None
    return None


async def revoke_refresh_token(token: str, redis) -> None:
    key = hashlib.sha256(token.encode()).hexdigest()
    subject = await redis.getdel(f"auth:refresh:{key}")
    if subject:
        await redis.srem(f"auth:refresh-index:{subject}", key)


async def revoke_user_refresh_tokens(user_id: UUID, redis) -> None:
    index = f"auth:refresh-index:{user_id}"
    keys = await redis.smembers(index) or []
    if keys:
        await redis.delete(*(f"auth:refresh:{key}" for key in keys))
    await redis.delete(index)


def unavailable(exc: RedisError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The authentication session store is unavailable.")

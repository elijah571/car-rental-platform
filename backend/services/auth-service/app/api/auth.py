from secrets import compare_digest
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis import RedisError, get_redis
from app.models import User
from app.repositories import UserRepository
from app.schemas.auth import (
    ConfirmSignUpRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    ResendCodeRequest,
    SignUpRequest,
    UserContactRead,
)
from app.services import email_sender, local_auth
from app.services.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


class PasswordResetRequest(BaseModel):
    email: EmailStr
    code: str | None = None
    new_password: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(customer|platform-admin)$")


def _access_claims(authorization: str | None):
    import jwt
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    try:
        return jwt.decode(authorization[7:], get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"], issuer="car-rental-auth", audience="car-rental-platform")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired.") from exc


def _require_admin(authorization: str | None):
    claims = _access_claims(authorization)
    if claims.get("role") != "platform-admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return claims


def _user_payload(user: User):
    return {"id": str(user.id), "email": user.email, "name": user.full_name, "role": user.role, "is_active": user.is_active, "is_email_verified": user.is_email_verified, "created_at": user.created_at}


def verify_internal_service_key(
    service_key: str | None = Header(default=None, alias="X-Auth-Service-Key"),
) -> None:
    configured = get_settings().auth_service_api_key
    if configured is None:
        raise HTTPException(status_code=503, detail="Auth service access is not configured.")
    if service_key is None or not compare_digest(service_key, configured.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid auth service credentials.")


@router.get("/internal/users/{auth_subject}/contact", response_model=UserContactRead)
async def get_user_contact(
    auth_subject: str,
    _: None = Depends(verify_internal_service_key),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepository(db).get_by_subject(auth_subject)
    if user is None or not user.is_active or not user.is_email_verified:
        raise HTTPException(status_code=404, detail="Verified user contact not found.")
    return UserContactRead(email=user.email)


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: SignUpRequest, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).strip().lower()
    repository = UserRepository(db)
    if await repository.get_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    settings = get_settings()
    role = "platform-admin" if email in settings.admin_email_set else "customer"
    user = await repository.create_user(
        auth_subject=str(uuid4()),
        email=email,
        full_name=payload.name,
        password_hash=await run_in_threadpool(hash_password, payload.password),
        role=role,
    )
    try:
        await db.commit()
        code = await local_auth.issue_verification_code(email, get_redis())
        if settings.smtp_configured:
            await run_in_threadpool(email_sender.send_verification_code, email, code)
    except RedisError as exc:
        await db.rollback()
        raise local_auth.unavailable(exc) from exc
    except Exception:
        # Keep the unverified account so the user can request another code.
        raise

    message = "Account created. Check your email for a verification code."
    if not settings.smtp_configured:
        if not settings.allow_dev_verification_code or settings.environment.lower() == "production":
            raise HTTPException(status_code=503, detail="Email verification is not configured.")
        return MessageResponse(message=message, verification_code=code)
    return MessageResponse(message=message)


@router.post("/confirm", response_model=MessageResponse)
async def confirm(payload: ConfirmSignUpRequest, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).strip().lower()
    redis = get_redis()
    try:
        attempts_key = f"auth:verify-attempts:{email}"
        attempts = await redis.incr(attempts_key)
        if attempts == 1:
            await redis.expire(attempts_key, 600)
        if attempts > 5:
            raise HTTPException(status_code=429, detail="Too many invalid verification attempts. Request a new code.")
        if not await local_auth.verify_code(email, payload.confirmation_code, redis):
            raise HTTPException(status_code=400, detail="The verification code is invalid or expired.")
        user = await UserRepository(db).set_email_verified(email, True)
        if user is None:
            raise HTTPException(status_code=404, detail="No account was found for this email.")
        await db.commit()
        await redis.delete(f"auth:verify:{email}")
        await redis.delete(attempts_key)
    except RedisError as exc:
        raise local_auth.unavailable(exc) from exc
    return MessageResponse(message="Email verified. You can now sign in.")


@router.post("/resend-code", response_model=MessageResponse)
async def resend_code(payload: ResendCodeRequest, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = await UserRepository(db).get_by_email(email)
    if user is None or user.is_email_verified:
        return MessageResponse(message="A verification code was sent if the account needs verification.")
    try:
        redis = get_redis()
        allowed = await redis.set(f"auth:resend-limit:{email}", "1", ex=60, nx=True)
        if not allowed:
            raise HTTPException(status_code=429, detail="Wait one minute before requesting another code.")
        code = await local_auth.issue_verification_code(email, redis)
    except RedisError as exc:
        raise local_auth.unavailable(exc) from exc
    settings = get_settings()
    if settings.smtp_configured:
        await run_in_threadpool(email_sender.send_verification_code, email, code)
        return MessageResponse(message="A new verification code was sent if the account needs verification.")
    if settings.allow_dev_verification_code and settings.environment.lower() != "production":
        return MessageResponse(message="Verification code generated for local development.", verification_code=code)
    raise HTTPException(status_code=503, detail="Email verification is not configured.")


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = await UserRepository(db).get_by_email(email)
    if user is None or not await run_in_threadpool(verify_password, payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="The email or password is incorrect.")
    if not user.is_email_verified:
        raise HTTPException(status_code=403, detail="Verify your email address before signing in.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled.")
    try:
        refresh_token = await local_auth.issue_refresh_token(user, get_redis())
    except RedisError as exc:
        raise local_auth.unavailable(exc) from exc
    return {
        "tokens": {
            "AccessToken": local_auth.create_access_token(user),
            "RefreshToken": refresh_token,
            "TokenType": "Bearer",
        },
        "user": {"id": str(user.id), "email": user.email, "name": user.full_name, "role": user.role},
    }


@router.post("/refresh")
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    redis = get_redis()
    try:
        subject = await local_auth.consume_refresh_token(payload.refresh_token, redis)
        user = await db.get(User, subject) if subject else None
        if user is None or not user.is_active or not user.is_email_verified:
            raise HTTPException(status_code=401, detail="The refresh token is invalid or expired.")
        new_refresh = await local_auth.issue_refresh_token(user, redis)
    except RedisError as exc:
        raise local_auth.unavailable(exc) from exc
    return {"tokens": {"AccessToken": local_auth.create_access_token(user), "RefreshToken": new_refresh, "TokenType": "Bearer"}}


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: LogoutRequest):
    try:
        await local_auth.revoke_refresh_token(payload.refresh_token, get_redis())
    except RedisError as exc:
        raise local_auth.unavailable(exc) from exc
    return MessageResponse(message="Signed out.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ResendCodeRequest, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = await UserRepository(db).get_by_email(email)
    generic = "If an active account exists for this email, a password reset code was sent."
    if user is None or not user.is_active or not user.is_email_verified:
        return MessageResponse(message=generic)
    settings = get_settings()
    try:
        redis = get_redis()
        allowed = await redis.set(f"auth:password-reset-limit:{email}", "1", ex=60, nx=True)
        if not allowed:
            raise HTTPException(status_code=429, detail="Wait one minute before requesting another reset code.")
        code = await local_auth.issue_reset_code(email, redis)
    except RedisError as exc:
        raise local_auth.unavailable(exc) from exc
    if settings.smtp_configured:
        await run_in_threadpool(email_sender.send_password_reset_code, email, code)
        return MessageResponse(message=generic)
    if settings.allow_dev_verification_code and settings.environment.lower() != "production":
        return MessageResponse(message="Password reset code generated for local development.", verification_code=code)
    raise HTTPException(status_code=503, detail="Password reset email is not configured.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    if not payload.code or not payload.new_password or len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="A reset code and password of at least 8 characters are required.")
    email = str(payload.email).strip().lower()
    redis = get_redis()
    try:
        attempts_key = f"auth:password-reset-attempts:{email}"
        attempts = await redis.incr(attempts_key)
        if attempts == 1:
            await redis.expire(attempts_key, 900)
        if attempts > 5:
            raise HTTPException(status_code=429, detail="Too many invalid reset attempts. Request a new code.")
        if not await local_auth.verify_reset_code(email, payload.code, redis):
            raise HTTPException(status_code=400, detail="The reset code is invalid or expired.")
        user = await UserRepository(db).get_by_email(email)
        if user is None or not user.is_active or not user.is_email_verified:
            raise HTTPException(status_code=400, detail="The reset code is invalid or expired.")
        await UserRepository(db).set_password_hash(user, await run_in_threadpool(hash_password, payload.new_password))
        await db.commit()
        await local_auth.revoke_user_refresh_tokens(user.id, redis)
        await redis.delete(f"auth:password-reset:{email}", attempts_key)
    except RedisError as exc:
        await db.rollback()
        raise local_auth.unavailable(exc) from exc
    return MessageResponse(message="Password updated. Sign in with your new password.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    import jwt
    from uuid import UUID

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to change your password.")
    try:
        claims = jwt.decode(authorization[7:], get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"], issuer="car-rental-auth", audience="car-rental-platform")
        user_id = UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired.") from exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found.")
    if not await run_in_threadpool(verify_password, payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Choose a password different from your current password.")
    await UserRepository(db).set_password_hash(user, await run_in_threadpool(hash_password, payload.new_password))
    await db.commit()
    try:
        await local_auth.revoke_user_refresh_tokens(user.id, get_redis())
    except RedisError as exc:
        raise local_auth.unavailable(exc) from exc
    return MessageResponse(message="Password changed. Sign in again with your new password.")


@router.get("/admin/users")
async def admin_list_users(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    _require_admin(authorization)
    users = (await db.scalars(select(User).order_by(User.created_at.desc()).limit(500))).all()
    return [_user_payload(user) for user in users]


@router.get("/admin/users/{user_id}")
async def admin_get_user(user_id: str, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    _require_admin(authorization)
    try:
        user = await db.get(User, UUID(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found.") from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return _user_payload(user)


@router.patch("/admin/users/{user_id}")
async def admin_update_user(user_id: str, payload: AdminUserUpdate, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    claims = _require_admin(authorization)
    try:
        user = await db.get(User, UUID(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found.") from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    values = payload.model_dump(exclude_unset=True)
    if claims.get("sub") == str(user.id) and values.get("is_active") is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")
    if claims.get("sub") == str(user.id) and values.get("role") not in (None, "platform-admin"):
        raise HTTPException(status_code=400, detail="You cannot remove your own administrator role.")
    for key, value in values.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return _user_payload(user)


@router.delete("/admin/users/{user_id}", status_code=204)
async def admin_delete_user(user_id: str, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    claims = _require_admin(authorization)
    try:
        user = await db.get(User, UUID(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found.") from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if claims.get("sub") == str(user.id):
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")
    user.is_active = False
    await db.commit()

import base64
import hashlib
import hmac
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.core.config import get_settings


@lru_cache
def _client():
    settings = get_settings()
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def _required_config() -> tuple[str, str, str | None]:
    settings = get_settings()
    if not settings.cognito_user_pool_id or not settings.cognito_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cognito is not configured. Set COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID.",
        )
    return (
        settings.cognito_user_pool_id,
        settings.cognito_client_id,
        settings.cognito_client_secret,
    )


def _secret_hash(username: str, client_id: str, client_secret: str | None) -> dict:
    if not client_secret:
        return {}
    digest = hmac.new(
        client_secret.encode(),
        (username + client_id).encode(),
        hashlib.sha256,
    ).digest()
    return {"SecretHash": base64.b64encode(digest).decode()}


def _call(operation: str, **kwargs):
    try:
        return getattr(_client(), operation)(**kwargs)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        messages = {
            "UsernameExistsException": (409, "An account with this email already exists."),
            "CodeMismatchException": (400, "The confirmation code is invalid."),
            "ExpiredCodeException": (400, "The confirmation code has expired."),
            "UserNotFoundException": (404, "No account was found for this email."),
            "NotAuthorizedException": (401, "The credentials or token are invalid."),
            "UserNotConfirmedException": (403, "Confirm your email address before signing in."),
            "InvalidPasswordException": (400, "The password does not meet the pool requirements."),
            "TooManyRequestsException": (429, "Too many requests. Try again shortly."),
            "LimitExceededException": (429, "The request limit was reached. Try again shortly."),
            "InvalidParameterException": (400, "The request is invalid."),
        }
        http_status, message = messages.get(code, (502, "Cognito could not complete the request."))
        raise HTTPException(status_code=http_status, detail=message) from exc
    except BotoCoreError as exc:
        raise HTTPException(status_code=502, detail="Cognito is currently unavailable.") from exc


def sign_up(email: str, password: str, name: str) -> dict:
    _, client_id, secret = _required_config()
    return _call(
        "sign_up",
        ClientId=client_id,
        Username=email,
        Password=password,
        UserAttributes=[{"Name": "email", "Value": email}, {"Name": "name", "Value": name}],
        **_secret_hash(email, client_id, secret),
    )


def confirm_sign_up(email: str, code: str) -> None:
    _, client_id, secret = _required_config()
    _call(
        "confirm_sign_up",
        ClientId=client_id,
        Username=email,
        ConfirmationCode=code,
        **_secret_hash(email, client_id, secret),
    )


def resend_code(email: str) -> None:
    _, client_id, secret = _required_config()
    _call(
        "resend_confirmation_code",
        ClientId=client_id,
        Username=email,
        **_secret_hash(email, client_id, secret),
    )


def login(email: str, password: str) -> dict:
    _, client_id, secret = _required_config()
    response = _call(
        "initiate_auth",
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": email,
            "PASSWORD": password,
            **({"SECRET_HASH": _secret_hash(email, client_id, secret)["SecretHash"]} if secret else {}),
        },
    )
    return response.get("AuthenticationResult", {})


def refresh(email: str, refresh_token: str) -> dict:
    _, client_id, secret = _required_config()
    response = _call(
        "initiate_auth",
        ClientId=client_id,
        AuthFlow="REFRESH_TOKEN_AUTH",
        AuthParameters={
            "REFRESH_TOKEN": refresh_token,
            **({"SECRET_HASH": _secret_hash(email, client_id, secret)["SecretHash"]} if secret else {}),
        },
    )
    return response.get("AuthenticationResult", {})


def logout(access_token: str) -> None:
    _call("global_sign_out", AccessToken=access_token)


def get_user(access_token: str) -> dict:
    return _call("get_user", AccessToken=access_token)


def close_client() -> None:
    if _client.cache_info().currsize:
        _client().close()
    _client.cache_clear()

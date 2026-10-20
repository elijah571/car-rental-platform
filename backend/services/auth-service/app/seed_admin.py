"""Create or reset an allowlisted local platform administrator interactively."""

import asyncio
from getpass import getpass
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import User
from app.repositories import UserRepository
from app.services.passwords import hash_password


async def seed_admin(email: str, password: str) -> None:
    settings = get_settings()
    normalized_email = email.strip().lower()
    if normalized_email not in settings.admin_email_set:
        raise SystemExit("That email is not listed in PLATFORM_ADMIN_EMAILS.")
    if len(password) < 8:
        raise SystemExit("The password must contain at least eight characters.")

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_email(normalized_email)
            if user is None:
                user = await repository.create_user(
                    auth_subject=str(uuid4()),
                    email=normalized_email,
                    full_name=normalized_email.partition("@")[0],
                    password_hash=hash_password(password),
                    role="platform-admin",
                )
                user.is_email_verified = True
                user.is_active = True
            else:
                user.password_hash = hash_password(password)
                user.role = "platform-admin"
                user.is_email_verified = True
                user.is_active = True
                user.auth_subject = str(user.id)
            await session.commit()
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    allowed = sorted(settings.admin_email_set)
    default = allowed[0] if len(allowed) == 1 else ""
    email = input(f"Admin email{f' [{default}]' if default else ''}: ").strip() or default
    password = getpass("Admin password: ")
    asyncio.run(seed_admin(email, password))
    print(f"Seeded platform administrator: {email.strip().lower()}")


if __name__ == "__main__":
    main()

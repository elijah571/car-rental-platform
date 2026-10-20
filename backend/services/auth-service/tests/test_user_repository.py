import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import User
from app.repositories import UserRepository


@pytest.mark.anyio
async def test_user_repository_sync_lookup_and_activation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repository = UserRepository(session)
        user = await repository.sync_cognito_profile(
            cognito_sub="cognito-sub-123",
            email="Renter@Example.com",
            full_name="Renter Example",
            is_email_verified=True,
        )
        await session.commit()

        assert user.email == "renter@example.com"
        assert user.is_email_verified is True
        assert await repository.get_by_email("RENTER@example.com") == user
        assert await repository.get_by_cognito_sub("cognito-sub-123") == user

        disabled = await repository.set_active("cognito-sub-123", False)
        await session.commit()
        assert disabled is user
        assert disabled.is_active is False
        assert await repository.set_active("missing-sub", False) is None

    await engine.dispose()


@pytest.mark.anyio
async def test_user_repository_rejects_email_linked_to_another_cognito_user():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repository = UserRepository(session)
        await repository.sync_cognito_profile(
            cognito_sub="original-sub",
            email="renter@example.com",
            full_name="Renter",
            is_email_verified=True,
        )
        await session.commit()

        with pytest.raises(ValueError, match="different Cognito account"):
            await repository.sync_cognito_profile(
                cognito_sub="different-sub",
                email="RENTER@example.com",
                full_name="Impostor",
                is_email_verified=True,
            )

    await engine.dispose()

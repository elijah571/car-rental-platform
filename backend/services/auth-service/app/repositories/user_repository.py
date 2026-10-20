from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    """Persistence operations for locally authenticated accounts."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_subject(self, subject: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.auth_subject == subject)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.strip().lower())
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        auth_subject: str,
        email: str,
        full_name: str,
        password_hash: str,
        role: str = "customer",
    ) -> User:
        """Create an account without committing the caller's transaction."""
        normalized_email = email.strip().lower()
        user = User(
            id=UUID(auth_subject),
            auth_subject=auth_subject,
            email=normalized_email,
            full_name=full_name.strip(),
            password_hash=password_hash,
            role=role,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def set_active(self, subject: str, is_active: bool) -> User | None:
        user = await self.get_by_subject(subject)
        if user is None:
            return None
        user.is_active = is_active
        await self.session.flush()
        return user

    async def set_email_verified(self, email: str, is_verified: bool) -> User | None:
        user = await self.get_by_email(email)
        if user is None:
            return None
        user.is_email_verified = is_verified
        await self.session.flush()
        return user

    async def set_password_hash(self, user: User, password_hash: str) -> None:
        user.password_hash = password_hash
        await self.session.flush()

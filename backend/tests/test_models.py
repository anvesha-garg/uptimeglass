import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import RefreshToken, User


async def test_user_gets_uuid_and_utc_timestamp(db_session):
    user = User(email="a@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)  # loads created_at, which the database filled in

    assert isinstance(user.id, uuid.UUID)
    assert user.created_at.tzinfo is not None


async def test_duplicate_email_is_rejected(db_session):
    db_session.add(User(email="same@example.com", password_hash="hash"))
    await db_session.commit()

    db_session.add(User(email="same@example.com", password_hash="hash"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_deleting_a_user_deletes_their_refresh_tokens(db_session):
    user = User(email="b@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()

    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db_session.commit()

    await db_session.delete(user)
    await db_session.commit()

    count = await db_session.scalar(select(func.count()).select_from(RefreshToken))
    assert count == 0

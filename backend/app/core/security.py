import hashlib, hmac, os, secrets
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.user import AuthSession, User

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 210_000)
    return f'{salt.hex()}:{digest.hex()}'

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(':', 1)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), 210_000).hex()
        return hmac.compare_digest(actual, digest_hex)
    except ValueError:
        return False

def new_token() -> str:
    return secrets.token_urlsafe(48)

async def current_user(authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentication required')
    token = authorization.removeprefix('Bearer ').strip()
    row = await session.execute(select(User).join(AuthSession, AuthSession.user_id == User.id).where(AuthSession.token == token))
    user = row.scalar_one_or_none()
    if not user:
        raise HTTPException(401, 'Invalid session')
    return user

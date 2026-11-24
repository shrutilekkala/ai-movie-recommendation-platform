from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import hash_password, verify_password, new_token, current_user
from app.db.session import get_db
from app.models.user import User, AuthSession
from app.schemas.user import RegisterIn, LoginIn, AuthOut, UserOut
router = APIRouter(prefix='/auth', tags=['auth'])

@router.post('/register', response_model=AuthOut)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.email == data.email.lower()))).scalar_one_or_none():
        raise HTTPException(409, 'Email already registered')
    user = User(email=data.email.lower(), display_name=data.display_name, password_hash=hash_password(data.password))
    db.add(user); await db.flush()
    token = new_token(); db.add(AuthSession(token=token, user_id=user.id)); await db.commit(); await db.refresh(user)
    return {'token': token, 'user': user}

@router.post('/login', response_model=AuthOut)
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == data.email.lower()))).scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash): raise HTTPException(401, 'Invalid email or password')
    token = new_token(); db.add(AuthSession(token=token, user_id=user.id)); await db.commit()
    return {'token': token, 'user': user}

@router.get('/me', response_model=UserOut)
async def me(user: User = Depends(current_user)): return user

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import current_user
from app.db.session import get_db
from app.models.content import Content
from app.models.user import User, UserContentState, InteractionEvent
from app.schemas.user import StatePatch, InteractionIn
from app.streaming.producer import publish_event
router = APIRouter(prefix='/me', tags=['personalization'])

async def get_state(db, user_id, content_id):
    return (await db.execute(select(UserContentState).where(UserContentState.user_id==user_id, UserContentState.content_id==content_id))).scalar_one_or_none()

@router.get('/library')
async def library(user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    rows=(await db.execute(select(Content,UserContentState).join(UserContentState,UserContentState.content_id==Content.id).where(UserContentState.user_id==user.id))).all()
    return [{'content': c, 'reaction': s.reaction, 'in_my_list': bool(s.in_my_list), 'progress_seconds': s.progress_seconds} for c,s in rows]

@router.patch('/content/{content_id}')
async def update_state(content_id:int, data:StatePatch, user:User=Depends(current_user), db:AsyncSession=Depends(get_db)):
    content=await db.get(Content,content_id)
    if not content: raise HTTPException(404,'Content not found')
    state=await get_state(db,user.id,content_id)
    if not state:
        state=UserContentState(user_id=user.id,content_id=content_id); db.add(state)
    if data.in_my_list is not None: state.in_my_list=int(data.in_my_list)
    if data.reaction is not None:
        if data.reaction not in ('like','dislike','none'): raise HTTPException(400,'reaction must be like, dislike, or none')
        state.reaction=None if data.reaction=='none' else data.reaction
    if data.progress_seconds is not None: state.progress_seconds=data.progress_seconds
    db.add(InteractionEvent(user_id=user.id,content_id=content_id,event_type='state_update',event_value=data.model_dump_json(exclude_none=True)))
    await db.commit(); await db.refresh(state)
    if data.reaction in ('like','dislike'):
        await publish_event({'user_id':user.id,'content_id':content_id,'event_type':data.reaction,'event_value':None})
    if data.in_my_list is not None:
        await publish_event({'user_id':user.id,'content_id':content_id,'event_type':'add_to_list' if data.in_my_list else 'remove_from_list','event_value':None})
    if data.progress_seconds is not None:
        await publish_event({'user_id':user.id,'content_id':content_id,'event_type':'watch_progress','event_value':str(data.progress_seconds)})
    return {'content_id':content_id,'reaction':state.reaction,'in_my_list':bool(state.in_my_list),'progress_seconds':state.progress_seconds}

@router.post('/events')
async def event(data:InteractionIn,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    db.add(InteractionEvent(user_id=user.id,content_id=data.content_id,event_type=data.event_type,event_value=data.event_value)); await db.commit()
    streamed=await publish_event({'user_id':user.id,'content_id':data.content_id,'event_type':data.event_type,'event_value':data.event_value})
    return {'recorded':True,'streamed':streamed}

@router.get('/events')
async def events(user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    rows=(await db.execute(select(InteractionEvent).where(InteractionEvent.user_id==user.id).order_by(InteractionEvent.created_at.desc()).limit(50))).scalars().all()
    return [{'id':x.id,'content_id':x.content_id,'event_type':x.event_type,'event_value':x.event_value,'created_at':x.created_at} for x in rows]

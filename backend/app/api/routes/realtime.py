import json
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from app.core.config import settings
from app.core.security import current_user
from app.models.user import User

router=APIRouter(prefix='/realtime',tags=['realtime-personalization'])

@router.get('/session')
async def session_features(user:User=Depends(current_user)):
    r=Redis.from_url(settings.redis_url,decode_responses=True); key=f'nexus:session:{user.id}'
    try:
        genres=await r.hgetall(f'{key}:genres'); meta=await r.hgetall(key); raw=await r.lrange(f'{key}:events',0,19)
        prefs=sorted(({'genre':g,'score':round(float(v),3)} for g,v in genres.items()),key=lambda x:x['score'],reverse=True)
        return {'event_count':int(meta.get('event_count',0)),'last_event_type':meta.get('last_event_type'),'updated_at':meta.get('updated_at'),'genre_affinity':prefs,'recent_events':[json.loads(x) for x in raw]}
    finally: await r.aclose()

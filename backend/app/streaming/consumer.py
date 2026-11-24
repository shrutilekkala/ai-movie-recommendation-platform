import asyncio, json
from datetime import datetime, timezone
from aiokafka import AIOKafkaConsumer
from redis.asyncio import Redis
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.content import Content

EVENT_WEIGHT={'play':0.35,'watch_progress':0.55,'complete':1.0,'like':1.25,'dislike':-1.35,'skip':-0.9,'add_to_list':0.7,'remove_from_list':-0.2,'search':0.15,'state_update':0.15}

async def process(redis:Redis,event:dict):
    uid=event.get('user_id'); cid=event.get('content_id'); et=event.get('event_type','unknown')
    if not uid: return
    key=f'nexus:session:{uid}'
    title=None; genre=None
    if cid:
        async with SessionLocal() as db:
            item=await db.get(Content,int(cid))
            if item: title=item.title; genre=item.genre
    weight=EVENT_WEIGHT.get(et,0.1)
    if genre:
        await redis.hincrbyfloat(f'{key}:genres',genre,weight)
    compact={'event_type':et,'content_id':cid,'title':title,'genre':genre,'weight':weight,'occurred_at':event.get('occurred_at') or datetime.now(timezone.utc).isoformat()}
    await redis.lpush(f'{key}:events',json.dumps(compact)); await redis.ltrim(f'{key}:events',0,49)
    await redis.hincrby(key,'event_count',1); await redis.hset(key,mapping={'last_event_type':et,'updated_at':compact['occurred_at']})
    await redis.expire(key,86400); await redis.expire(f'{key}:genres',86400); await redis.expire(f'{key}:events',86400)

async def main():
    redis=Redis.from_url(settings.redis_url,decode_responses=True)
    consumer=AIOKafkaConsumer(settings.kafka_topic,bootstrap_servers=settings.kafka_bootstrap_servers,group_id='nexus-session-features-v1',auto_offset_reset='earliest',enable_auto_commit=True)
    await consumer.start(); print('NEXUS realtime consumer ready')
    try:
        async for msg in consumer:
            try: await process(redis,json.loads(msg.value.decode('utf-8')))
            except Exception as exc: print('event processing error',exc)
    finally:
        await consumer.stop(); await redis.aclose()

if __name__=='__main__': asyncio.run(main())

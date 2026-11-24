import json
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
from app.core.config import settings

async def publish_event(payload: dict) -> bool:
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    try:
        await producer.start()
        body = {**payload, 'occurred_at': datetime.now(timezone.utc).isoformat()}
        await producer.send_and_wait(settings.kafka_topic, json.dumps(body).encode('utf-8'))
        return True
    except Exception:
        return False
    finally:
        try: await producer.stop()
        except Exception: pass

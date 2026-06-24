"""
Webhook worker for ScrapAI CLI.

Dramatiq actor that delivers webhook notifications.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import dramatiq
import httpx
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries

from core.db import SessionLocal

from ..services.redis_config import get_redis_config

logger = logging.getLogger(__name__)

_redis_config = get_redis_config()
broker = RedisBroker(
    host=_redis_config.host,
    port=_redis_config.port,
    db=_redis_config.db,
    password=_redis_config.password if _redis_config.password else None,
    ssl=_redis_config.ssl,
    middleware=[
        Retries(max_retries=5, min_backoff=5000, max_backoff=300000),
    ],
)
dramatiq.set_broker(broker)

queue_name = _redis_config.get_queue_name("webhook")


@dramatiq.actor(queue_name=queue_name, max_retries=5)
def webhook_actor(delivery_id: int):
    """
    Deliver a webhook notification.

    This actor sends HTTP POST requests to webhook endpoints.
    """
    db = SessionLocal()

    try:
        from core.models import WebhookDelivery, WebhookSubscription

        delivery = db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()

        if not delivery:
            logger.error(f"Webhook delivery {delivery_id} not found")
            return

        subscription = (
            db.query(WebhookSubscription)
            .filter(WebhookSubscription.id == delivery.subscription_id)
            .first()
        )

        if not subscription or not subscription.active:
            logger.warning(f"Webhook subscription {delivery.subscription_id} not active")
            delivery.status = "cancelled"
            db.commit()
            return

        delivery.status = "delivering"
        delivery.attempt += 1
        db.commit()

        payload = delivery.payload
        payload_str = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

        signature = hmac.new(
            subscription.secret.encode(), payload_str.encode(), hashlib.sha256
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Event": delivery.event_type,
            "X-Webhook-Delivery": str(delivery.id),
            # Backward-compatible aliases for any early consumers of the worker.
            "X-ScrapAI-Signature": f"sha256={signature}",
            "X-ScrapAI-Event": delivery.event_type,
            "X-ScrapAI-Delivery": str(delivery.id),
        }

        timeout = httpx.Timeout(30.0, connect=10.0)

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                subscription.target_url,
                content=payload_str,
                headers=headers,
            )

        delivery.response_status = response.status_code
        delivery.delivered_at = datetime.now(timezone.utc)

        if 200 <= response.status_code < 300:
            delivery.status = "delivered"
            logger.info(f"Webhook {delivery_id} delivered to {subscription.target_url}")
        else:
            delivery.status = "failed"
            delivery.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
            logger.warning(f"Webhook {delivery_id} failed with status {response.status_code}")

        db.commit()

    except httpx.TimeoutException as e:
        logger.error(f"Webhook {delivery_id} timed out: {e}")
        delivery.status = "failed"
        delivery.error_message = f"Timeout: {str(e)}"
        db.commit()
        raise

    except httpx.RequestError as e:
        logger.error(f"Webhook {delivery_id} request error: {e}")
        delivery.status = "failed"
        delivery.error_message = f"Request error: {str(e)}"
        db.commit()
        raise

    except Exception as e:
        logger.error(f"Webhook {delivery_id} failed with exception: {e}")
        try:
            delivery.status = "failed"
            delivery.error_message = str(e)[:500]
            db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()


def enqueue_webhook_delivery(delivery_id: int):
    """
    Enqueue a webhook delivery for execution.
    """
    logger.info(f"Enqueueing webhook delivery {delivery_id}")
    webhook_actor.send(delivery_id)

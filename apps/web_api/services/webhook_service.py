"""
Webhook delivery service for ScrapAI CLI.

Provides webhook subscription, delivery, and retry logic.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from core.db import get_db
from core.models import WebhookDelivery, WebhookSubscription

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for managing webhook subscriptions and deliveries."""

    def create_subscription(
        self,
        db: Session,
        project: str,
        target_url: str,
        event_types: List[str],
        secret: Optional[str] = None,
    ) -> WebhookSubscription:
        """Create a new webhook subscription."""
        existing = (
            db.query(WebhookSubscription)
            .filter(
                WebhookSubscription.project == project,
                WebhookSubscription.target_url == target_url,
            )
            .first()
        )

        if existing:
            raise ValueError(f"Webhook subscription already exists for {target_url}")

        if not secret:
            import secrets

            secret = secrets.token_hex(32)

        subscription = WebhookSubscription(
            project=project,
            target_url=target_url,
            event_types=event_types,
            secret=secret,
            active=True,
        )

        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        logger.info(f"Created webhook subscription {subscription.id} for {target_url}")
        return subscription

    def list_subscriptions(
        self, db: Session, project: str, active_only: bool = True
    ) -> List[WebhookSubscription]:
        """List webhook subscriptions for a project."""
        query = db.query(WebhookSubscription).filter(WebhookSubscription.project == project)

        if active_only:
            query = query.filter(WebhookSubscription.active.is_(True))

        return query.order_by(WebhookSubscription.created_at.desc()).all()

    def get_active_webhooks(
        self, db: Session, project: str, event_type: Optional[str] = None
    ) -> List[WebhookSubscription]:
        """Get active webhooks for a project, optionally filtered by event type."""
        query = db.query(WebhookSubscription).filter(
            WebhookSubscription.project == project,
            WebhookSubscription.active.is_(True),
        )

        webhooks = query.all()

        if event_type:
            webhooks = [w for w in webhooks if event_type in (w.event_types or [])]

        return webhooks

    def queue_webhook_delivery(
        self, db: Session, subscription_id: int, payload: Dict[str, Any]
    ) -> Optional[WebhookDelivery]:
        """Queue a webhook delivery for later processing."""
        subscription = self.get_subscription(db, subscription_id)

        if not subscription or not subscription.active:
            return None

        delivery = WebhookDelivery(
            subscription_id=subscription_id,
            event_type=payload.get("event_type") or payload.get("event", "unknown"),
            payload=payload,
            status="pending",
        )

        db.add(delivery)
        db.commit()
        db.refresh(delivery)

        try:
            from ..workers.webhook_worker import enqueue_webhook_delivery

            enqueue_webhook_delivery(delivery.id)
        except Exception as e:
            logger.error(f"Failed to enqueue webhook delivery: {e}")

        return delivery

    def get_subscription(self, db: Session, subscription_id: int) -> Optional[WebhookSubscription]:
        """Get a webhook subscription by ID."""
        return (
            db.query(WebhookSubscription).filter(WebhookSubscription.id == subscription_id).first()
        )

    def delete_subscription(self, db: Session, subscription_id: int) -> bool:
        """Delete a webhook subscription."""
        subscription = self.get_subscription(db, subscription_id)

        if not subscription:
            return False

        db.delete(subscription)
        db.commit()

        logger.info(f"Deleted webhook subscription {subscription_id}")
        return True

    def deliver_webhook(
        self, subscription_id: int, event_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Deliver a webhook to a subscription."""
        db = next(get_db())

        try:
            subscription = self.get_subscription(db, subscription_id)

            if not subscription:
                logger.error(f"Subscription {subscription_id} not found")
                return False

            if not subscription.active:
                logger.warning(f"Subscription {subscription_id} is inactive")
                return False

            if event_type not in subscription.event_types:
                logger.warning(f"Event type {event_type} not in subscription {subscription_id}")
                return False

            delivery = WebhookDelivery(
                subscription_id=subscription_id,
                event_type=event_type,
                payload=payload,
                status="pending",
            )

            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            self._enqueue_delivery(delivery.id)

            return True

        except Exception as e:
            logger.error(f"Failed to deliver webhook: {e}")
            return False
        finally:
            db.close()

    def _enqueue_delivery(self, delivery_id: int) -> None:
        """Enqueue webhook delivery via Dramatiq."""
        try:
            from .redis_config import get_dramatiq_broker

            broker = get_dramatiq_broker()

            queue_name = f"{broker.prefix}:webhook"

            broker.enqueue(
                actor_name="webhook_delivery_actor",
                args=[delivery_id],
                queue_name=queue_name,
            )

            logger.info(f"Enqueued webhook delivery {delivery_id}")

        except Exception as e:
            logger.error(f"Failed to enqueue webhook delivery: {e}")

    def _send_webhook(self, delivery_id: int) -> None:
        """Send webhook HTTP request."""
        db = next(get_db())

        try:
            delivery = db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()

            if not delivery:
                logger.error(f"Webhook delivery {delivery_id} not found")
                return

            subscription = self.get_subscription(db, delivery.subscription_id)

            if not subscription:
                logger.error(f"Subscription {delivery.subscription_id} not found")
                delivery.status = "failed"
                delivery.error_message = "Subscription not found"
                db.commit()
                return

            timestamp = int(time.time())
            payload_str = json.dumps(delivery.payload, sort_keys=True)

            signature = hmac.new(
                subscription.secret.encode(), payload_str.encode(), hashlib.sha256
            ).hexdigest()

            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={signature}",
                "X-Webhook-Timestamp": str(timestamp),
                "X-Webhook-Event": delivery.event_type,
            }

            try:
                response = requests.post(
                    subscription.target_url,
                    json=delivery.payload,
                    headers=headers,
                    timeout=30,
                )

                if 200 <= response.status_code < 300:
                    delivery.status = "delivered"
                    delivery.delivered_at = datetime.now(timezone.utc)
                    delivery.response_status = response.status_code
                    logger.info(
                        f"Webhook {delivery_id} delivered successfully to {subscription.target_url}"
                    )
                else:
                    delivery.status = "failed"
                    delivery.response_status = response.status_code
                    delivery.error_message = f"HTTP {response.status_code}"
                    logger.error(f"Webhook {delivery_id} failed with status {response.status_code}")
                    self._schedule_retry(delivery)

                db.commit()

            except requests.exceptions.Timeout:
                delivery.status = "failed"
                delivery.error_message = "Request timeout"
                logger.error(f"Webhook {delivery_id} timed out")
                self._schedule_retry(delivery)
                db.commit()

            except Exception as e:
                delivery.status = "failed"
                delivery.error_message = str(e)
                logger.error(f"Webhook {delivery_id} failed: {e}")
                self._schedule_retry(delivery)
                db.commit()

        except Exception as e:
            logger.error(f"Failed to send webhook {delivery_id}: {e}")
        finally:
            db.close()

    def _schedule_retry(self, delivery: WebhookDelivery) -> None:
        """Schedule webhook retry using exponential backoff."""
        if delivery.attempt >= 3:
            logger.warning(f"Webhook delivery {delivery.id} exceeded max retries")
            return

        retry_delay = min(60 * (2**delivery.attempt), 600)

        try:
            from .redis_config import get_dramatiq_broker

            broker = get_dramatiq_broker()
            queue_name = f"{broker.prefix}:webhook"

            broker.enqueue(
                actor_name="webhook_delivery_actor",
                args=[delivery.id],
                queue_name=queue_name,
                delay=retry_delay * 1000,
            )

            logger.info(f"Scheduled retry for webhook {delivery.id} in {retry_delay}s")

        except Exception as e:
            logger.error(f"Failed to schedule webhook retry: {e}")

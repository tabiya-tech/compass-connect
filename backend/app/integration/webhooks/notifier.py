"""
Sends the webhook notifications. When something happens, `emit` records a delivery; the retry loop calls `attempt`,
which sends the deliveries that are due until the platform takes them or the retry period is over. The first attempt
and the retries are the same code. Nothing here is specific to one event: see events.py.
"""

import logging
import uuid
from datetime import timedelta, datetime
from typing import Any, Mapping, Optional

import httpx
from pydantic import SecretStr

from app.integration.repository import ExternalUserRepository
from app.integration.webhooks.events import WebhookEventDefinition, DataNotReadyError
from app.integration.webhooks.jwe import encrypt_webhook_payload
from app.integration.webhooks.repository import WebhookDeliveryRepository
from app.integration.webhooks.types import WebhookEvent, WebhookDelivery, DeliveryStatus, WebhookNotification
from common_libs.time_utilities import get_now, truncate_microseconds

RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2),
                timedelta(hours=6), timedelta(hours=12))
"""
The waits after each failed attempt: 7 attempts over about 21 hours, then the delivery is failed.
"""

ATTEMPT_LEASE = timedelta(minutes=1)
"""
How long an attempt holds its delivery. Longer than the request timeout plus building the data.
"""

REQUEST_TIMEOUT_SECONDS = 10
CONTENT_TYPE = "application/jose"
DELIVERY_ID_HEADER = "X-Compass-Delivery-Id"


def _now() -> datetime:
    # MongoDB keeps milliseconds
    return truncate_microseconds(get_now())


class WebhookNotifier:
    def __init__(self, *,
                 users: ExternalUserRepository,
                 deliveries: WebhookDeliveryRepository,
                 events: list[WebhookEventDefinition],
                 http_client: httpx.AsyncClient,
                 enabled: bool,
                 retry_delays: tuple[timedelta, ...] = RETRY_DELAYS):
        self._users = users
        self._deliveries = deliveries
        self._events = {definition.event: definition for definition in events}
        self._http_client = http_client
        self._enabled = enabled
        self._retry_delays = retry_delays
        self._logger = logging.getLogger(self.__class__.__name__)

    async def emit(self, event: WebhookEvent, user_id: str, event_ref: Mapping[str, Any]) -> Optional[str]:
        """
        Record a notification for the platform of the user, if the user was created by one with a webhook and
        webhooks are enabled. It is sent by the next `attempt`. Never raises: the caller's work must not fail because
        of a webhook.

        :param user_id: the Compass user id
        :param event_ref: what identifies the event, see WebhookEventDefinition.build_data
        :return: the delivery id, or None if nothing is notified
        """
        if not self._enabled:
            return None
        try:
            external_user = await self._users.find_by_user_id(user_id)
            if external_user is None or external_user.webhook is None:
                return None
            now = _now()
            delivery = WebhookDelivery(id=str(uuid.uuid4()), event=event, external_id=external_user.external_id,
                                       event_ref=dict(event_ref), status=DeliveryStatus.PENDING,
                                       next_attempt_at=now, lease_until=now, created_at=now)
            if not await self._deliveries.insert(delivery):
                return None
            return delivery.id
        except Exception:  # pylint: disable=broad-except
            self._logger.exception("Could not record a %s webhook delivery", event.value)
            return None

    async def attempt(self) -> bool:
        """
        Send the delivery due the longest, unless another attempt holds it. Nothing is sent while webhooks are not
        enabled: deliveries recorded before they were turned off stay pending, and are sent if they are turned on again.

        :return: whether a delivery was attempted (False: none is due, or webhooks are not enabled)
        """
        if not self._enabled:
            return False
        delivery = await self._deliveries.claim(_now(), ATTEMPT_LEASE)
        if delivery is None:
            return False
        await self._send(delivery)
        return True

    async def _send(self, delivery: WebhookDelivery) -> None:
        now = _now()
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.last_status_code = None
        delivery.lease_until = now  # released when saved: the next attempt, if any, waits for next_attempt_at

        external_user = await self._users.find_by_external_id(delivery.external_id)
        if external_user is None or external_user.webhook is None:
            # the platform removed it: nowhere to send it to, and it does not want it
            delivery.status, delivery.last_error = DeliveryStatus.FAILED, "webhook removed"
            await self._deliveries.save_outcome(delivery)
            return

        delivery.url = external_user.webhook.url
        delivery.last_error = await self._post(delivery, external_user.webhook.secret, now)
        if delivery.last_error is None:
            delivery.status = DeliveryStatus.DELIVERED
            self._logger.info("Webhook delivery %s delivered (attempt %d)", delivery.id, delivery.attempts)
        elif delivery.attempts > len(self._retry_delays):
            delivery.status = DeliveryStatus.FAILED
            self._logger.warning("Webhook delivery %s failed after %d attempts: %s", delivery.id, delivery.attempts,
                                 delivery.last_error)
        else:
            delivery.next_attempt_at = now + self._retry_delays[delivery.attempts - 1]
            self._logger.warning("Webhook delivery %s attempt %d failed: %s, next at %s", delivery.id,
                                 delivery.attempts, delivery.last_error, delivery.next_attempt_at.isoformat())
        await self._deliveries.save_outcome(delivery)

    async def _post(self, delivery: WebhookDelivery, secret: SecretStr, now: datetime) -> Optional[str]:
        """
        Build the notification, encrypt it and POST it.

        :return: None if the platform took it, else why not (never the response body: it is the platform's)
        """
        definition = self._events[delivery.event]
        try:
            data = await definition.build_data(delivery.external_id, delivery.event_ref)
            notification = WebhookNotification(event=delivery.event, version=definition.version,
                                               delivery_id=delivery.id, sent_at=now,
                                               external_id=delivery.external_id, data=data)
            response = await self._http_client.post(
                delivery.url, content=encrypt_webhook_payload(notification, secret),
                headers={"Content-Type": CONTENT_TYPE, DELIVERY_ID_HEADER: delivery.id},
                timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)
        except (DataNotReadyError, httpx.HTTPError) as e:
            # expected: retried later, the warning of the attempt is enough
            return "timeout" if isinstance(e, httpx.TimeoutException) else type(e).__name__
        except Exception as e:  # pylint: disable=broad-except
            # a bug, not the platform: still retried, like a platform that is down
            self._logger.exception("Could not send the webhook delivery %s", delivery.id)
            return type(e).__name__
        delivery.last_status_code = response.status_code
        return None if response.is_success else f"HTTP {response.status_code}"

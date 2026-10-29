import asyncio
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Awaitable, Mapping, Optional

import httpx
import pytest
import pytest_mock
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.integration.repository import ExternalUserRepository
from app.integration.types import ExternalUser, Webhook
from app.integration.webhooks.events import WebhookEventDefinition, DataNotReadyError
from app.integration.webhooks.notifier import WebhookNotifier, RETRY_DELAYS
from app.integration.webhooks.repository import WebhookDeliveryRepository
from app.integration.webhooks.testing import decrypt
from app.integration.webhooks.types import WebhookEvent, DeliveryStatus, WebhookNotification
from common_libs.time_utilities import get_now, truncate_microseconds

_URL = "https://api.partner.example.org/hook"
_RETRY_AT_ONCE = (timedelta(0), timedelta(0))
"""
Two retries without waiting: 3 attempts in all.
"""


class _FakeEvent(WebhookEventDefinition):
    """
    An event with nothing of conversation.completed but its name: the notifier must need nothing else.
    """
    event = WebhookEvent.CONVERSATION_COMPLETED
    version = 7

    def __init__(self):
        self.data = {"answer": 42}
        self.ready = True

    async def build_data(self, external_id: str, event_ref: Mapping[str, Any]) -> dict[str, Any]:
        if not self.ready:
            raise DataNotReadyError("not yet")
        return {**self.data, "for": external_id, "ref": dict(event_ref)}


class _Platform:
    """
    The platform's server. Records the requests it gets and answers 200 until told otherwise.
    """

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self._answer = httpx.Response(200)
        self._error: Optional[type[httpx.HTTPError]] = None

    def answers(self, status_code: int, **kwargs):
        self._answer, self._error = httpx.Response(status_code, **kwargs), None

    def is_down(self):
        self._error = httpx.ConnectError

    def is_slow(self):
        self._error = httpx.ReadTimeout

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._error is not None:
            raise self._error("simulated", request=request)
        return self._answer


@dataclass
class _Setup:
    db: AsyncIOMotorDatabase
    users: ExternalUserRepository
    deliveries: WebhookDeliveryRepository
    platform: _Platform
    event: _FakeEvent
    secret: str
    notifier: WebhookNotifier
    """
    Retries at once (_RETRY_AT_ONCE), so a test does not wait.
    """

    def new_notifier(self, *, enabled: bool = True,
                     retry_delays: tuple[timedelta, ...] = _RETRY_AT_ONCE) -> WebhookNotifier:
        return WebhookNotifier(users=self.users, deliveries=self.deliveries, events=[self.event],
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.platform.handle)),
                               enabled=enabled, retry_delays=retry_delays)

    async def stored(self, delivery_id: str):
        return await self.deliveries.find_by_id(delivery_id)


async def _add_external_user(users: ExternalUserRepository, external_id: str, user_id: str,
                             webhook: Optional[Webhook]) -> None:
    now = truncate_microseconds(get_now())
    await users.insert(ExternalUser(external_id=external_id, email=f"{external_id}@example.com", user_id=user_id,
                                    created_at=now, updated_at=now))
    await users.set_webhook(external_id, webhook, now)


@pytest.fixture(scope="function")
async def setup(in_memory_application_database: Awaitable[AsyncIOMotorDatabase]) -> _Setup:
    """
    The external user ext-1 (Compass user uid-1), whose platform has a webhook.
    """
    db = await in_memory_application_database
    users = ExternalUserRepository(db)
    secret = secrets.token_urlsafe(32)
    await _add_external_user(users, "ext-1", "uid-1", Webhook(url=_URL, secret=secret))
    s = _Setup(db=db, users=users, deliveries=WebhookDeliveryRepository(db), platform=_Platform(), event=_FakeEvent(),
               secret=secret, notifier=None)  # type: ignore[arg-type]
    s.notifier = s.new_notifier()
    return s


def _opened(request: httpx.Request, secret: str) -> WebhookNotification:
    _, plaintext = decrypt(request.content.decode("ascii"), secret)
    return WebhookNotification.model_validate_json(plaintext)


async def _count_deliveries(s: _Setup) -> int:
    return await s.db.get_collection("webhook_deliveries").count_documents({})


class TestEmit:
    @pytest.mark.asyncio
    async def test_records_the_delivery_and_sends_nothing_yet(self, setup: Awaitable[_Setup]):
        s = await setup
        # WHEN something happens to a user whose platform has a webhook
        actual_id = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})

        # THEN a pending delivery is recorded, due now, and nothing is sent: the next attempt sends it
        actual = await s.stored(actual_id)
        assert actual.status == DeliveryStatus.PENDING
        assert actual.external_id == "ext-1"
        assert actual.event_ref == {"session_id": 1}
        assert actual.attempts == 0
        assert actual.next_attempt_at == actual.created_at
        assert s.platform.requests == []

    @pytest.mark.asyncio
    async def test_the_same_event_is_recorded_once(self, setup: Awaitable[_Setup]):
        s = await setup
        actual_first = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})
        actual_again = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})
        actual_other = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 2})

        assert actual_first is not None
        assert actual_again is None
        assert actual_other is not None
        assert await _count_deliveries(s) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_user_id", ["uid-2", "uid-not-external"],
                             ids=["external user without a webhook", "not an external user"])
    async def test_nothing_for_a_user_without_a_webhook(self, setup: Awaitable[_Setup], given_user_id: str):
        s = await setup
        await _add_external_user(s.users, "ext-2", "uid-2", webhook=None)

        actual = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, given_user_id, {"session_id": 1})

        assert actual is None
        assert await _count_deliveries(s) == 0

    @pytest.mark.asyncio
    async def test_nothing_while_webhooks_are_not_enabled(self, setup: Awaitable[_Setup]):
        s = await setup
        notifier = s.new_notifier(enabled=False)

        actual = await notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})

        assert actual is None
        assert await _count_deliveries(s) == 0

    @pytest.mark.asyncio
    async def test_never_raises(self, setup: Awaitable[_Setup], mocker: pytest_mock.MockerFixture):
        # the caller is the user's last chat turn: a webhook problem must not fail it
        s = await setup
        mocker.patch.object(s.users, "find_by_user_id", side_effect=RuntimeError("database down"))

        actual = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})

        assert actual is None


class TestAttempt:
    @pytest.mark.asyncio
    async def test_sends_the_encrypted_notification(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a recorded delivery
        given_id = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})

        # WHEN it is attempted
        assert await s.notifier.attempt() is True

        # THEN the platform gets one POST to its URL, with the delivery id in clear and the JWE as body
        assert len(s.platform.requests) == 1
        actual_request = s.platform.requests[0]
        assert str(actual_request.url) == _URL
        assert actual_request.headers["Content-Type"] == "application/jose"
        assert actual_request.headers["X-Compass-Delivery-Id"] == given_id

        # AND decrypting it with its secret gives the envelope, with the event's data for this user and event
        actual = _opened(actual_request, s.secret)
        assert actual.event == WebhookEvent.CONVERSATION_COMPLETED
        assert actual.version == 7
        assert actual.delivery_id == given_id
        assert actual.external_id == "ext-1"
        assert actual.data == {"answer": 42, "for": "ext-1", "ref": {"session_id": 1}}

        # AND the delivery is stored as delivered
        actual_delivery = await s.stored(given_id)
        assert actual_delivery.status == DeliveryStatus.DELIVERED
        assert actual_delivery.attempts == 1
        assert actual_delivery.url == _URL
        assert actual_delivery.last_status_code == 200
        assert actual_delivery.last_error is None

    @pytest.mark.asyncio
    async def test_nothing_to_attempt(self, setup: Awaitable[_Setup]):
        s = await setup
        assert await s.notifier.attempt() is False
        assert s.platform.requests == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_platform, expected_status_code, expected_error", [
        (lambda platform: platform.answers(500), 500, "HTTP 500"),
        (lambda platform: platform.answers(404), 404, "HTTP 404"),
        (lambda platform: platform.answers(302, headers={"Location": "https://other.example.org/"}), 302, "HTTP 302"),
        (lambda platform: platform.is_slow(), None, "timeout"),
        (lambda platform: platform.is_down(), None, "ConnectError"),
    ], ids=["server error", "client error", "redirect (not followed)", "too slow", "down"])
    async def test_a_failed_attempt_is_retried_later(self, setup: Awaitable[_Setup], given_platform,
                                                      expected_status_code: Optional[int], expected_error: str):
        s = await setup
        # GIVEN a recorded delivery, the real retry delays, and a platform that does not take it
        notifier = s.new_notifier(retry_delays=RETRY_DELAYS)
        given_id = await notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})
        given_platform(s.platform)

        # WHEN it is attempted
        await notifier.attempt()

        # THEN why it failed is stored, and the next attempt is after the first retry delay
        actual = await s.stored(given_id)
        assert actual.status == DeliveryStatus.PENDING
        assert actual.attempts == 1
        assert actual.last_status_code == expected_status_code
        assert actual.last_error == expected_error
        assert actual.next_attempt_at == actual.last_attempt_at + RETRY_DELAYS[0]
        # AND it is not attempted again before then (and a redirect was not followed)
        assert await notifier.attempt() is False
        assert len(s.platform.requests) == 1

    @pytest.mark.asyncio
    async def test_failed_after_the_last_retry(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a recorded delivery and a platform that stays down
        given_id = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})
        s.platform.answers(503)

        # WHEN it is attempted until nothing is due any more
        while await s.notifier.attempt():
            pass

        # THEN it was attempted 3 times (the first and two retries), always with the same delivery id, and is failed
        assert len(s.platform.requests) == 3
        assert {request.headers["X-Compass-Delivery-Id"] for request in s.platform.requests} == {given_id}
        actual = await s.stored(given_id)
        assert actual.status == DeliveryStatus.FAILED
        assert actual.attempts == 3
        assert actual.last_error == "HTTP 503"

    @pytest.mark.asyncio
    async def test_a_retry_uses_the_current_webhook_and_data(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a first attempt that failed
        given_id = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})
        s.platform.answers(500)
        await s.notifier.attempt()

        # WHEN the platform changes its webhook, the data changes, and the delivery is retried
        given_secret = secrets.token_urlsafe(32)
        await s.users.set_webhook("ext-1", Webhook(url=f"{_URL}/v2", secret=given_secret), get_now())
        s.event.data = {"answer": 43}
        s.platform.answers(204)
        await s.notifier.attempt()

        # THEN it goes to the new URL, encrypted with the new secret, with the current data
        actual_request = s.platform.requests[-1]
        assert str(actual_request.url) == f"{_URL}/v2"
        assert _opened(actual_request, given_secret).data["answer"] == 43
        assert (await s.stored(given_id)).status == DeliveryStatus.DELIVERED

    @pytest.mark.asyncio
    async def test_failed_when_the_platform_removed_its_webhook(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a recorded delivery, then the platform removes its webhook
        given_id = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})
        await s.users.set_webhook("ext-1", None, get_now())

        # WHEN it is attempted
        await s.notifier.attempt()

        # THEN nothing is sent, and it is failed
        assert s.platform.requests == []
        actual = await s.stored(given_id)
        assert actual.status == DeliveryStatus.FAILED
        assert actual.last_error == "webhook removed"

    @pytest.mark.asyncio
    async def test_retried_when_the_data_is_not_ready(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a recorded delivery whose data cannot be built yet (e.g. the results could not be read)
        given_id = await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})
        s.event.ready = False

        # WHEN it is attempted
        await s.notifier.attempt()

        # THEN nothing is sent, and it is retried later
        assert s.platform.requests == []
        actual = await s.stored(given_id)
        assert actual.status == DeliveryStatus.PENDING
        assert actual.last_error == "DataNotReadyError"

    @pytest.mark.asyncio
    async def test_attempts_at_the_same_time_send_it_once(self, setup: Awaitable[_Setup]):
        s = await setup
        # GIVEN a recorded delivery
        await s.notifier.emit(WebhookEvent.CONVERSATION_COMPLETED, "uid-1", {"session_id": 1})

        # WHEN four backend instances attempt at the same time
        actual = await asyncio.gather(*(s.new_notifier().attempt() for _ in range(4)))

        # THEN only one of them sends it
        assert actual.count(True) == 1
        assert len(s.platform.requests) == 1

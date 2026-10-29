import asyncio

import httpx

from app.app_config import get_application_config
from app.integration.repository import ExternalUserRepository
from app.integration.service import ExternalUserResultsReader
from app.integration.webhooks.events import ConversationCompleted
from app.integration.webhooks.notifier import WebhookNotifier
from app.integration.webhooks.repository import WebhookDeliveryRepository
from app.server_dependencies.db_dependencies import CompassDBProvider
from app.store.database_application_state_store import DatabaseApplicationStateStore
from app.users.get_user_preferences_repository import get_user_preferences_repository

# Lock to ensure that the singleton instance is thread-safe
_webhook_notifier_lock = asyncio.Lock()
_webhook_notifier_singleton: WebhookNotifier | None = None


async def get_webhook_notifier() -> WebhookNotifier:
    """
    One notifier for the process, with one HTTP client, so the connections to the platform are reused.
    No FastAPI dependencies: the retry loop uses it outside of a request.
    """
    global _webhook_notifier_singleton
    if _webhook_notifier_singleton is None:  # without the lock once created (the lock is expensive)
        async with _webhook_notifier_lock:
            if _webhook_notifier_singleton is None:  # check again, holding the lock
                application_db = await CompassDBProvider.get_application_db()
                users = ExternalUserRepository(application_db)
                results = ExternalUserResultsReader(
                    user_repository=users,
                    user_preferences_repository=await get_user_preferences_repository(application_db),
                    application_state_store=DatabaseApplicationStateStore(application_db))
                _webhook_notifier_singleton = WebhookNotifier(
                    users=users,
                    deliveries=WebhookDeliveryRepository(application_db),
                    events=[ConversationCompleted(results.get_results)],
                    http_client=httpx.AsyncClient(),
                    enabled=get_application_config().integration_webhooks_enabled)
    return _webhook_notifier_singleton

import pytest
from pydantic import ValidationError

from app.app_config import ApplicationConfig


class TestIntegrationWebhooks:
    def test_enabled_needs_allowed_origins(self, setup_application_config: ApplicationConfig):
        # an instance that would accept webhooks but could not call any server fails at start-up, not on a request
        with pytest.raises(ValidationError, match="BACKEND_INTEGRATION_WEBHOOK_URL_ORIGINS"):
            ApplicationConfig.model_validate({**dict(setup_application_config), "integration_webhooks_enabled": True})

    def test_enabled_with_allowed_origins(self, setup_application_config: ApplicationConfig):
        actual = ApplicationConfig.model_validate({**dict(setup_application_config),
                                                   "integration_webhooks_enabled": True,
                                                   "integration_webhook_url_origins": ["https://api.example.org"]})
        assert actual.integration_webhooks_enabled is True

    def test_disabled_by_default(self, setup_application_config: ApplicationConfig):
        assert setup_application_config.integration_webhooks_enabled is False

from typing import Optional

import pytest

from app.gateway.ingress_mode import (IngressMode, get_ingress_mode, get_rate_limit_per_minute, validate_ingress_config,
                                      DEFAULT_RATE_LIMIT_PER_MINUTE)


@pytest.fixture(scope="function")
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in ["INGRESS_MODE", "FIREBASE_PROJECT_ID", "BACKEND_RATE_LIMIT_PER_MINUTE"]:
        monkeypatch.delenv(name, raising=False)


class TestGetIngressMode:
    @pytest.mark.parametrize("given_value, expected_mode", [
        (None, IngressMode.GATEWAY),
        ("", IngressMode.GATEWAY),
        ("gateway", IngressMode.GATEWAY),
        ("direct", IngressMode.DIRECT),
        (" Direct ", IngressMode.DIRECT),
    ])
    def test_valid_values(self, clean_env, monkeypatch: pytest.MonkeyPatch, given_value: Optional[str], expected_mode: IngressMode):
        # GIVEN INGRESS_MODE set to a valid value, or not set
        if given_value is not None:
            monkeypatch.setenv("INGRESS_MODE", given_value)

        # WHEN getting the ingress mode
        # THEN it is the expected one, the gateway by default
        assert get_ingress_mode() == expected_mode

    @pytest.mark.parametrize("given_value", ["selfhosted", "foo"])
    def test_unknown_value(self, clean_env, monkeypatch: pytest.MonkeyPatch, given_value: str):
        # GIVEN INGRESS_MODE set to an unknown value
        monkeypatch.setenv("INGRESS_MODE", given_value)

        # WHEN getting the ingress mode
        # THEN it fails with a message naming the variable and the allowed values
        with pytest.raises(ValueError) as error_info:
            get_ingress_mode()
        assert "INGRESS_MODE" in str(error_info.value)
        assert "gateway, direct" in str(error_info.value)


class TestGetRateLimitPerMinute:
    @pytest.mark.parametrize("given_value, expected_limit", [
        (None, DEFAULT_RATE_LIMIT_PER_MINUTE),
        ("", DEFAULT_RATE_LIMIT_PER_MINUTE),
        ("0", 0),
        (" 120 ", 120),
    ])
    def test_valid_values(self, clean_env, monkeypatch: pytest.MonkeyPatch, given_value: Optional[str], expected_limit: int):
        # GIVEN BACKEND_RATE_LIMIT_PER_MINUTE set to a valid value, or not set
        if given_value is not None:
            monkeypatch.setenv("BACKEND_RATE_LIMIT_PER_MINUTE", given_value)

        # WHEN getting the rate limit
        # THEN it is the expected one, the default when not set
        assert get_rate_limit_per_minute() == expected_limit

    @pytest.mark.parametrize("given_value", ["abc", "-1", "1.5"])
    def test_invalid_values(self, clean_env, monkeypatch: pytest.MonkeyPatch, given_value: str):
        # GIVEN BACKEND_RATE_LIMIT_PER_MINUTE set to an invalid value
        monkeypatch.setenv("BACKEND_RATE_LIMIT_PER_MINUTE", given_value)

        # WHEN getting the rate limit
        # THEN it fails with a message naming the variable
        with pytest.raises(ValueError) as error_info:
            get_rate_limit_per_minute()
        assert "BACKEND_RATE_LIMIT_PER_MINUTE" in str(error_info.value)


class TestValidateIngressConfig:
    def test_direct_with_firebase_project_id(self, clean_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the direct mode with a FIREBASE_PROJECT_ID
        monkeypatch.setenv("INGRESS_MODE", "direct")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "test-project")

        # WHEN validating the configuration
        # THEN it passes
        validate_ingress_config()

    def test_direct_requires_firebase_project_id(self, clean_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the direct mode without a FIREBASE_PROJECT_ID
        monkeypatch.setenv("INGRESS_MODE", "direct")

        # WHEN validating the configuration
        # THEN it fails with a message naming the missing variable
        with pytest.raises(ValueError) as error_info:
            validate_ingress_config()
        assert "FIREBASE_PROJECT_ID" in str(error_info.value)

    def test_direct_rejects_an_invalid_rate_limit(self, clean_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the direct mode with an invalid rate limit
        monkeypatch.setenv("INGRESS_MODE", "direct")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "test-project")
        monkeypatch.setenv("BACKEND_RATE_LIMIT_PER_MINUTE", "abc")

        # WHEN validating the configuration
        # THEN it fails
        with pytest.raises(ValueError):
            validate_ingress_config()

    def test_gateway_needs_neither_firebase_project_id_nor_rate_limit(self, clean_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN the gateway mode, without a FIREBASE_PROJECT_ID, and a rate limit that is not used
        monkeypatch.setenv("INGRESS_MODE", "gateway")
        monkeypatch.setenv("BACKEND_RATE_LIMIT_PER_MINUTE", "abc")

        # WHEN validating the configuration
        # THEN it passes
        validate_ingress_config()

    def test_unknown_mode_is_rejected(self, clean_env, monkeypatch: pytest.MonkeyPatch):
        # GIVEN an unknown ingress mode
        monkeypatch.setenv("INGRESS_MODE", "selfhosted")

        # WHEN validating the configuration
        # THEN it fails
        with pytest.raises(ValueError):
            validate_ingress_config()

import jwt
import pytest

import app.gateway.firebase_tokens as firebase_tokens_module
from app.gateway.firebase_tokens import _FirebasePublicKeys

_KEY_ID = "test-key-id"


class TestFirebasePublicKeys:
    @staticmethod
    def _provider(monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> tuple[_FirebasePublicKeys, list[int]]:
        provider = _FirebasePublicKeys("https://example.invalid/jwks")
        fetches: list[int] = []

        def _fake_fetch():
            fetches.append(1)
            provider._keys = {_KEY_ID: "public-key"}  # pylint: disable=protected-access
            provider._fetched_at = clock[0]  # pylint: disable=protected-access

        monkeypatch.setattr(provider, "_fetch", _fake_fetch)
        monkeypatch.setattr(firebase_tokens_module.time, "monotonic", lambda: clock[0])
        return provider, fetches

    def test_keys_are_cached(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN a provider
        provider, fetches = self._provider(monkeypatch, [1000.0])

        # WHEN asking for the same key several times
        for _ in range(5):
            assert provider.get_key(_KEY_ID) == "public-key"

        # THEN the keys are fetched only once
        assert len(fetches) == 1

    def test_unknown_key_ids_do_not_cause_a_fetch_storm(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN a provider with the keys already fetched
        clock = [1000.0]
        provider, fetches = self._provider(monkeypatch, clock)
        provider.get_key(_KEY_ID)

        # WHEN many unknown key ids are requested within the minimum refetch window
        for index in range(20):
            clock[0] += 1
            with pytest.raises(jwt.InvalidTokenError):
                provider.get_key(f"random-{index}")

        # THEN there is no additional fetch
        assert len(fetches) == 1

        # AND after the window an unknown key triggers one refetch (Google rotated keys)
        clock[0] += 61
        with pytest.raises(jwt.InvalidTokenError):
            provider.get_key("random-after-window")
        assert len(fetches) == 2

    def test_keys_expire(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN a provider with keys fetched
        clock = [1000.0]
        provider, fetches = self._provider(monkeypatch, clock)
        provider.get_key(_KEY_ID)

        # WHEN the cache lifetime has passed
        clock[0] += 3601
        provider.get_key(_KEY_ID)

        # THEN the keys are fetched again
        assert len(fetches) == 2

    def test_failed_refresh_keeps_using_the_cached_keys_and_is_throttled(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN a provider with fetched keys, whose cache has expired and whose next fetches fail
        clock = [1000.0]
        provider, fetches = self._provider(monkeypatch, clock)
        provider.get_key(_KEY_ID)
        failures: list[int] = []

        def _failing_fetch():
            failures.append(1)
            raise OSError("network unreachable")

        monkeypatch.setattr(provider, "_fetch", _failing_fetch)
        clock[0] += 3601

        # WHEN keys are requested repeatedly
        for _ in range(10):
            # THEN the cached key is still served
            assert provider.get_key(_KEY_ID) == "public-key"

        # AND only one refresh was attempted within the retry window
        assert len(failures) == 1
        assert len(fetches) == 1

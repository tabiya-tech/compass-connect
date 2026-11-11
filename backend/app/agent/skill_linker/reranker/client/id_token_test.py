import time
from unittest.mock import patch

import pytest

from app.agent.skill_linker.reranker.client import GoogleIdTokenProvider, IdTokenError


def _patch_fetch(*tokens: str):
    """Fetch the given tokens in order, without calling Google."""
    return patch("app.agent.skill_linker.reranker.client.id_token._fetch_id_token", side_effect=list(tokens))


def _patch_expiry(*expires_at: float):
    """Decode the expiry of the fetched tokens to the given timestamps."""
    return patch("app.agent.skill_linker.reranker.client.id_token.google.auth.jwt.decode",
                 side_effect=[{"exp": exp} for exp in expires_at])


class TestGetToken:
    @pytest.mark.asyncio
    async def test_caches_the_token_until_shortly_before_it_expires(self):
        # GIVEN a token that expires in an hour
        given_provider = GoogleIdTokenProvider(audience="https://reranker.test")

        # WHEN the token is requested twice
        with _patch_fetch("token-1", "token-2") as fetch, _patch_expiry(time.time() + 3600):
            actual_tokens = [await given_provider.get_token(), await given_provider.get_token()]

        # THEN it is fetched once, for the audience
        assert actual_tokens == ["token-1", "token-1"]
        fetch.assert_called_once_with("https://reranker.test")

    @pytest.mark.asyncio
    async def test_refreshes_a_token_about_to_expire(self):
        # GIVEN a token that expires in a minute
        given_provider = GoogleIdTokenProvider(audience="https://reranker.test")

        # WHEN the token is requested twice
        with _patch_fetch("token-1", "token-2"), _patch_expiry(time.time() + 60, time.time() + 3600):
            actual_tokens = [await given_provider.get_token(), await given_provider.get_token()]

        # THEN a new token is fetched the second time
        assert actual_tokens == ["token-1", "token-2"]

    @pytest.mark.asyncio
    async def test_raises_id_token_error_on_failure(self):
        # GIVEN no credentials to fetch a token with
        given_provider = GoogleIdTokenProvider(audience="https://reranker.test")

        # WHEN the token is requested
        # THEN an IdTokenError is raised
        with patch("app.agent.skill_linker.reranker.client.id_token._fetch_id_token", side_effect=Exception("no creds")):
            with pytest.raises(IdTokenError):
                await given_provider.get_token()

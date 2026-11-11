import logging
from typing import Optional

import httpx
from pydantic import ValidationError

from app.agent.skill_linker.reranker.client.id_token import GoogleIdTokenProvider, IdTokenError
from app.agent.skill_linker.reranker.client.response import RerankSkillsResponse
from app.agent.skill_linker.reranker.client.types import RerankCandidate


class LlmRerankerServiceError(Exception):
    """Raised when an LLM reranker request fails (authentication, HTTP, transport, or response shape)."""


class LlmRerankerClient:
    """
    Transport-only client for the LLM reranker API (https://<host>/openapi.json).
    The service runs on Cloud Run with authenticated invocation, authentication is via a Google ID token.
    """

    def __init__(self, *, base_url: str, token_provider: GoogleIdTokenProvider, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._timeout = timeout
        self._logger = logging.getLogger(self.__class__.__name__)

    async def rank_skills(self, *,
                          title: str,
                          company: Optional[str],
                          work_type: Optional[str],
                          responsibilities: list[str],
                          candidates: list[RerankCandidate],
                          max_skills: int) -> RerankSkillsResponse:
        url = f"{self._base_url}/rank/skills"
        payload = {
            "experience": {
                "title": title,
                "company": company,
                "work_type": work_type,
                "responsibilities": responsibilities,
            },
            "candidates": [candidate.model_dump() for candidate in candidates],
            "max_skills": max_skills,
        }
        try:
            token = await self._token_provider.get_token()
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=self._timeout
                )
                response.raise_for_status()
                return RerankSkillsResponse.model_validate(response.json())
        except IdTokenError as e:
            raise LlmRerankerServiceError(f"Failed to authenticate to the LLM reranker on {url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise LlmRerankerServiceError(
                f"LLM reranker returned HTTP {e.response.status_code} on {url}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise LlmRerankerServiceError(f"Failed to connect to the LLM reranker on {url}: {e}") from e
        except ValidationError as e:
            raise LlmRerankerServiceError(
                f"LLM reranker response from {url} does not match {RerankSkillsResponse.__name__}: {e}") from e

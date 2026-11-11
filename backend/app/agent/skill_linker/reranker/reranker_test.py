from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.reranker import LlmRerankerClient, SkillReranker
from app.agent.skill_linker.reranker.client import RerankSkillsResponse
from app.vector_search.esco_entities import SkillEntity


def _skill(uuid: str, score: float) -> SkillEntity:
    return SkillEntity(id="", UUID=uuid, preferredLabel=f"label {uuid}", altLabels=[],
                       description=f"description {uuid}", skillType="skill/competence", score=score)


def _given_client(ranked_ids: list[str]) -> MagicMock:
    client = MagicMock(spec=LlmRerankerClient)
    client.rank_skills = AsyncMock(return_value=RerankSkillsResponse(ranked_ids=ranked_ids))
    return client


class TestRerank:
    @pytest.mark.asyncio
    async def test_sends_the_experience_and_the_candidates(self):
        # GIVEN a reranker client
        given_client = _given_client(ranked_ids=[])
        reranker = SkillReranker(client=given_client)

        # WHEN two candidates are reranked
        await reranker.rerank(experience_title="Baker", responsibilities=["I bake bread"], company_name="Bakery",
                              work_type=WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT,
                              candidates=[_skill("a", 0.9), _skill("b", 0.5)], max_skills=3)

        # THEN the client gets the experience and the candidates, identified by their UUID
        actual_kwargs = given_client.rank_skills.call_args.kwargs
        assert actual_kwargs["title"] == "Baker"
        assert actual_kwargs["company"] == "Bakery"
        assert actual_kwargs["work_type"] == "Formal sector/Wage employment"
        assert actual_kwargs["responsibilities"] == ["I bake bread"]
        assert [(c.id, c.label, c.description, c.score) for c in actual_kwargs["candidates"]] == [
            ("a", "label a", "description a", 0.9),
            ("b", "label b", "description b", 0.5),
        ]
        assert actual_kwargs["max_skills"] == 3

    @pytest.mark.asyncio
    async def test_returns_the_ranked_candidates_in_order(self):
        # GIVEN a reranker that ranks b before a, and returns an id it was not given
        reranker = SkillReranker(client=_given_client(ranked_ids=["b", "unknown", "a"]))

        # WHEN the candidates are reranked
        actual_skills = await reranker.rerank(experience_title="Baker", responsibilities=[], company_name=None,
                                              work_type=None, candidates=[_skill("a", 0.9), _skill("b", 0.5),
                                                                          _skill("c", 0.4)], max_skills=5)

        # THEN the ranked candidates are returned in the reranker's order, ignoring the unknown id
        assert [skill.UUID for skill in actual_skills] == ["b", "a"]

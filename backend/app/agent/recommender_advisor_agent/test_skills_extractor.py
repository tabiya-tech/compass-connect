import pytest

from app.agent.recommender_advisor_agent.skills_extractor import SkillAggregation
from app.vector_search.esco_entities import SkillEntity


def _given_skill_entity(*, origin_uuid):
    return SkillEntity(
        id="skill_001",
        modelId="test_model",
        UUID="uuid_001",
        preferredLabel="Customer Service",
        altLabels=[],
        description="",
        scopeNote="",
        originUUID=origin_uuid,
        UUIDHistory=[],
        score=0.8,
        skillType="skill/competence",
    )


@pytest.mark.parametrize("missing_origin_uuid", [None, ""])
def test_to_dict_falls_back_to_uuid_when_origin_uuid_is_missing(missing_origin_uuid):
    # GIVEN a SkillEntity persisted without an originUUID (legacy data)
    skill = _given_skill_entity(origin_uuid=missing_origin_uuid)
    aggregation = SkillAggregation(skill_entity=skill, scores=[0.7], frequency=1, from_top_skills=1)

    # WHEN it is converted to the skills_vector dict consumed by the matching service
    actual = aggregation.to_dict(total_experiences=1)

    # THEN origin_uuid is the skill's UUID, never null or empty — the matching service
    # requires originUUID: str and rejects null with HTTP 422.
    assert actual["origin_uuid"] == "uuid_001"


def test_to_dict_preserves_origin_uuid_when_present():
    # GIVEN a SkillEntity with a real originUUID
    skill = _given_skill_entity(origin_uuid="origin_001")
    aggregation = SkillAggregation(skill_entity=skill, scores=[0.7], frequency=1, from_top_skills=1)

    # WHEN converted to dict
    actual = aggregation.to_dict(total_experiences=1)

    # THEN the original value is preserved (fallback only kicks in for None/empty)
    assert actual["origin_uuid"] == "origin_001"

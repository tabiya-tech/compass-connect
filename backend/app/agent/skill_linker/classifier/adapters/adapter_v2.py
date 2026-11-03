from typing import Optional, cast

from app.agent.skill_linker.classifier.adapters.adapter import EXTRACT_ENTITIES, ClassifierMatches, \
    IClassifierAdapter, to_description, to_title_candidates
from app.agent.skill_linker.classifier.config import ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.client import ClassifierClient, ClassifierV2Response
from app.agent.skill_linker.classifier.skill_ranking import SkillCandidate
from app.vector_search.esco_entities import SkillEntity, SkillTypeLiteral

_SKILL_TYPES: set[str] = {"skill/competence", "knowledge", "language", "attitude"}


class ClassifierAdapterV2(IClassifierAdapter):
    """
    Adapter for the /v2/classify endpoint, which returns the taxonomy entities (UUIDs, labels, ...) of the matches,
    so they are mapped directly to skill entities.
    """

    def __init__(self, *, client: ClassifierClient, config: ClassifierSkillLinkerConfig):
        self._client = client
        self._config = config

    async def classify(self, *, experience_title: str, responsibilities: list[str]) -> ClassifierMatches:
        response: ClassifierV2Response = await self._client.classify_v2(
            title=experience_title,
            description=to_description(responsibilities),
            extract_entities=EXTRACT_ENTITIES,
            top_k=self._config.top_k_per_entity,
            min_similarity=self._config.min_similarity
        )

        skill_candidates: list[SkillCandidate] = []
        occupation_matches: list[tuple[float, str]] = []
        for entity in response.entities:
            matches = sorted(entity.matches, key=lambda m: m.similarity_score, reverse=True)
            if entity.entity_type == "occupation":
                if matches:
                    occupation_matches.append((matches[0].similarity_score, matches[0].entity.preferred_label))
                continue
            if entity.entity_type != "skill":
                continue
            for index, match in enumerate(matches):
                taxonomy_entity = match.entity
                skill = SkillEntity(
                    # The classifier does not expose the database id of the skill
                    id="",
                    modelId=response.metadata.taxonomy_model_id,
                    UUID=taxonomy_entity.uuid,
                    preferredLabel=taxonomy_entity.preferred_label,
                    altLabels=taxonomy_entity.alt_labels,
                    description=taxonomy_entity.description,
                    originUUID=taxonomy_entity.origin_uuid,
                    UUIDHistory=taxonomy_entity.uuid_history,
                    skillType=_to_skill_type(taxonomy_entity.skill_type),
                    score=match.similarity_score
                )
                skill_candidates.append(SkillCandidate(skill=skill, is_best_match=index == 0))

        return ClassifierMatches(skill_candidates=skill_candidates,
                                 title_candidates=to_title_candidates(occupation_matches))


def _to_skill_type(skill_type: Optional[str]) -> SkillTypeLiteral:
    if skill_type in _SKILL_TYPES:
        return cast(SkillTypeLiteral, skill_type)
    return ""

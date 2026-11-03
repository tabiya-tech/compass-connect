import asyncio
import logging
from typing import Optional

from app.agent.skill_linker.classifier.adapters.adapter import EXTRACT_ENTITIES, ClassifierMatches, \
    IClassifierAdapter, to_description, to_title_candidates
from app.agent.skill_linker.classifier.config import ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.client import ClassifierClient, ClassifierV1Response
from app.agent.skill_linker.classifier.skill_ranking import SkillCandidate
from app.vector_search.esco_entities import SkillEntity
from app.vector_search.esco_search_service import SkillSearchService


class ClassifierAdapterV1(IClassifierAdapter):
    """
    Adapter for the /v1/classify endpoint, which only returns the labels of the matches,
    so they are resolved against the taxonomy using the skill search service.
    """

    def __init__(self, *,
                 client: ClassifierClient,
                 config: ClassifierSkillLinkerConfig,
                 skill_search_service: SkillSearchService):
        self._client = client
        self._config = config
        self._skill_search_service = skill_search_service
        self._logger = logging.getLogger(self.__class__.__name__)

    async def classify(self, *, experience_title: str, responsibilities: list[str]) -> ClassifierMatches:
        response: ClassifierV1Response = await self._client.classify_v1(
            title=experience_title,
            description=to_description(responsibilities),
            extract_entities=EXTRACT_ENTITIES,
            top_k=self._config.top_k_per_entity,
            min_similarity=self._config.min_similarity
        )

        # (label, score, is_best_match) of the matched skills
        skill_matches: list[tuple[str, float, bool]] = []
        occupation_matches: list[tuple[float, str]] = []
        for entity in response.classification.entities:
            matches = [(label, score) for label, score in map(_label_and_score, entity.linked_entities or []) if label]
            matches.sort(key=lambda m: m[1], reverse=True)
            if entity.entity_type == "occupation":
                if matches:
                    occupation_matches.append((matches[0][1], matches[0][0]))
                continue
            if entity.entity_type != "skill":
                continue
            skill_matches.extend((label, score, index == 0) for index, (label, score) in enumerate(matches))

        # resolve the labels against the taxonomy, once per distinct label
        distinct_labels = list(dict.fromkeys(label for label, _, _ in skill_matches))
        resolved = await asyncio.gather(*[self._resolve_skill_label(label) for label in distinct_labels])
        skill_by_label = dict(zip(distinct_labels, resolved))

        skill_candidates: list[SkillCandidate] = []
        for label, score, is_best_match in skill_matches:
            skill = skill_by_label.get(label)
            if skill is None:
                self._logger.warning("Could not resolve the classifier skill label '%s' to a taxonomy skill", label)
                continue
            skill_candidates.append(SkillCandidate(skill=skill.model_copy(update={"score": score}),
                                                   is_best_match=is_best_match))

        return ClassifierMatches(skill_candidates=skill_candidates,
                                 title_candidates=to_title_candidates(occupation_matches))

    async def _resolve_skill_label(self, label: str) -> Optional[SkillEntity]:
        candidates = await self._skill_search_service.search(query=label, k=5)
        if not candidates:
            return None
        # prefer an exact label match, otherwise trust the semantic search
        normalized_label = label.strip().lower()
        for candidate in candidates:
            labels = [candidate.preferredLabel, *candidate.altLabels]
            if any(normalized_label == candidate_label.strip().lower() for candidate_label in labels):
                return candidate
        return candidates[0]


def _label_and_score(linked_entity: dict) -> tuple[str, float]:
    label = linked_entity.get("label") or linked_entity.get("preferred_label") or ""
    score = linked_entity.get("similarity_score") or linked_entity.get("score") or 0.0
    return str(label).strip(), float(score)

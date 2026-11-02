import asyncio
import json
import logging
from typing import Optional, cast

from pydantic import BaseModel, ConfigDict, Field

from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier.classifier_client import ClassifierClient, ClassifierServiceError, \
    ClassifierV1Response, ClassifierV2Response
from app.agent.skill_linker.skill_linker import ISkillLinker, SkillLinkerResponse
from app.agent.skill_linker.skill_linker_type import SkillLinkerType
from app.countries import Country
from app.vector_search.esco_entities import SkillEntity, SkillTypeLiteral
from app.vector_search.esco_search_service import SkillSearchService
from common_libs.observability.tracing import traced_observation, update_observation

_SKILL_TYPES: set[str] = {"skill/competence", "knowledge", "language", "attitude"}


class ClassifierSkillLinkerConfig(BaseModel):
    number_of_top_skills: int = Field(default=5, gt=0)
    """
    The number of skills returned as the top skills of the experience.
    """

    top_k_per_entity: int = Field(default=3, ge=1, le=50)
    """
    The number of taxonomy matches the classifier returns for each extracted entity.
    The best match of each entity is a top skill candidate, the others end up in the remaining skills.
    """

    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    """
    Matches with a similarity score lower than this are dropped by the classifier.
    """

    model_config = ConfigDict(extra="forbid")


class _RankedSkill(BaseModel):
    skill: SkillEntity
    is_best_match: bool
    """
    Whether the skill was the best match for one of the extracted entities.
    """


class ClassifierSkillLinker(ISkillLinker):
    """
    Skill linker backed by the Tabiya classifier API, which extracts entities (skills, occupations) from the
    experience and links them to the taxonomy in a single call.

    - v2 returns the taxonomy entities (UUIDs, labels, ...) of the matches, so they are mapped directly.
    - v1 only returns the labels of the matches, so they are resolved against the taxonomy using the skill search service.
    """

    def __init__(self, *,
                 version: SkillLinkerType,
                 client: ClassifierClient,
                 skill_search_service: Optional[SkillSearchService] = None,
                 config: Optional[ClassifierSkillLinkerConfig] = None):
        if not version.is_classifier:
            raise ValueError(f"ClassifierSkillLinker does not support the skill linker type: {version.value}")
        if version == SkillLinkerType.CLASSIFIER_V1 and skill_search_service is None:
            raise ValueError("The classifier v1 skill linker requires a skill search service to resolve the matched labels")

        self._version = version
        self._client = client
        self._skill_search_service = skill_search_service
        self._config = config or ClassifierSkillLinkerConfig()
        self._logger = logging.getLogger(self.__class__.__name__)

    async def execute(self, *,
                      experience_title: str,
                      responsibilities: list[str],
                      company_name: Optional[str],
                      country_of_interest: Country,
                      work_type: WorkType) -> SkillLinkerResponse:
        with traced_observation(
                name="classifier_skill_linker",
                as_type="chain",
                input={"experience_title": experience_title, "responsibilities": responsibilities},
                metadata={"version": self._version.value},
        ) as observation:
            try:
                if self._version == SkillLinkerType.CLASSIFIER_V2:
                    ranked_skills, title_candidates = await self._classify_v2(experience_title, responsibilities)
                else:
                    ranked_skills, title_candidates = await self._classify_v1(experience_title, responsibilities)
            except ClassifierServiceError as e:
                # Do not break the conversation if the classifier is unavailable, behave like a linker that found nothing.
                self._logger.error("Failed to link skills for experience title: '%s'. Error: %s",
                                   experience_title, e, exc_info=e)
                return SkillLinkerResponse(top_skills=[], remaining_skills=[])

            response = self._to_response(ranked_skills, title_candidates)
            update_observation(observation, output={
                "top_skills": [skill.preferredLabel for skill in response.top_skills],
                "remaining_skills_count": len(response.remaining_skills),
            })
            if self._logger.isEnabledFor(logging.INFO):
                self._logger.info("Classifier (%s) linked experience '%s' to top skills: %s",
                                  self._version.value, experience_title,
                                  json.dumps([skill.preferredLabel for skill in response.top_skills], ensure_ascii=False))
            return response

    async def _classify_v2(self, experience_title: str, responsibilities: list[str]) -> tuple[list[_RankedSkill], list[str]]:
        response: ClassifierV2Response = await self._client.classify_v2(
            title=experience_title,
            description=_to_description(responsibilities),
            extract_entities=["skill", "occupation"],
            top_k=self._config.top_k_per_entity,
            min_similarity=self._config.min_similarity
        )

        ranked_skills: list[_RankedSkill] = []
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
                ranked_skills.append(_RankedSkill(skill=skill, is_best_match=index == 0))

        return ranked_skills, _to_title_candidates(occupation_matches)

    async def _classify_v1(self, experience_title: str, responsibilities: list[str]) -> tuple[list[_RankedSkill], list[str]]:
        response: ClassifierV1Response = await self._client.classify_v1(
            title=experience_title,
            description=_to_description(responsibilities),
            extract_entities=["skill", "occupation"],
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

        ranked_skills: list[_RankedSkill] = []
        for label, score, is_best_match in skill_matches:
            skill = skill_by_label.get(label)
            if skill is None:
                self._logger.warning("Could not resolve the classifier skill label '%s' to a taxonomy skill", label)
                continue
            ranked_skills.append(_RankedSkill(skill=skill.model_copy(update={"score": score}), is_best_match=is_best_match))

        return ranked_skills, _to_title_candidates(occupation_matches)

    async def _resolve_skill_label(self, label: str) -> Optional[SkillEntity]:
        candidates = await cast(SkillSearchService, self._skill_search_service).search(query=label, k=5)
        if not candidates:
            return None
        # prefer an exact label match, otherwise trust the semantic search
        normalized_label = label.strip().lower()
        for candidate in candidates:
            labels = [candidate.preferredLabel, *candidate.altLabels]
            if any(normalized_label == candidate_label.strip().lower() for candidate_label in labels):
                return candidate
        return candidates[0]

    def _to_response(self, ranked_skills: list[_RankedSkill], title_candidates: list[str]) -> SkillLinkerResponse:
        # Deduplicate by UUID, keeping the highest score. A skill is a top skill candidate
        # if it was the best match of at least one extracted entity.
        best_by_uuid: dict[str, _RankedSkill] = {}
        for ranked in ranked_skills:
            existing = best_by_uuid.get(ranked.skill.UUID)
            if existing is None:
                best_by_uuid[ranked.skill.UUID] = ranked
                continue
            best_by_uuid[ranked.skill.UUID] = _RankedSkill(
                skill=ranked.skill if ranked.skill.score > existing.skill.score else existing.skill,
                is_best_match=ranked.is_best_match or existing.is_best_match
            )

        by_score = sorted(best_by_uuid.values(), key=lambda r: r.skill.score, reverse=True)
        top_skill_candidates = [r.skill for r in by_score if r.is_best_match]
        top_skills = top_skill_candidates[:self._config.number_of_top_skills]
        top_skills_uuids = {skill.UUID for skill in top_skills}
        remaining_skills = [r.skill for r in by_score if r.skill.UUID not in top_skills_uuids]

        return SkillLinkerResponse(
            top_skills=top_skills,
            remaining_skills=remaining_skills,
            title_candidates=title_candidates
        )


def _to_description(responsibilities: list[str]) -> str:
    return "\n".join(f"- {responsibility}" for responsibility in responsibilities)


def _to_skill_type(skill_type: Optional[str]) -> SkillTypeLiteral:
    if skill_type in _SKILL_TYPES:
        return cast(SkillTypeLiteral, skill_type)
    return ""


def _label_and_score(linked_entity: dict) -> tuple[str, float]:
    label = linked_entity.get("label") or linked_entity.get("preferred_label") or ""
    score = linked_entity.get("similarity_score") or linked_entity.get("score") or 0.0
    return str(label).strip(), float(score)


def _to_title_candidates(occupation_matches: list[tuple[float, str]]) -> list[str]:
    labels = [label for _, label in sorted(occupation_matches, key=lambda m: m[0], reverse=True)]
    return list(dict.fromkeys(labels))

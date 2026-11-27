import asyncio
import json
import logging
from typing import Optional

from app.agent.agent_types import LLMStats
from app.agent.experience.timeline import Timeline
from app.agent.experience.work_type import WorkType
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2, \
    IClassifierAdapter
from app.agent.skill_linker.classifier.adapters.adapter import OccupationMatch
from app.agent.skill_linker.classifier.config import ClassifierSkillLinkerConfig
from app.agent.skill_linker.classifier.client import ClassifierApiVersion, ClassifierClient, ClassifierServiceError
from app.agent.skill_linker.classifier.overview_generator import ExperienceOverviewGenerator, ExperienceOverviewResult
from app.agent.skill_linker.classifier.skill_ranking import SkillCandidate, deduplicate_candidates, rank_skills
from app.agent.skill_linker.linker import ISkillLinker, SkillLinkerResponse
from app.agent.skill_linker.reranker import LlmRerankerServiceError, SkillReranker
from app.countries import Country
from app.vector_search.esco_entities import AssociatedSkillEntity, OccupationSkillEntity, SkillEntity
from app.vector_search.esco_search_service import OccupationSkillSearchService, SkillSearchService
from common_libs.observability.tracing import traced_observation, update_observation


class ClassifierSkillLinker(ISkillLinker):
    """
    Skill linker backed by the Tabiya classifier API, which extracts entities (skills, occupations) from the
    experience and links them to the taxonomy in a single call.

    The API version specific work is delegated to an adapter (see ClassifierAdapterV1 and ClassifierAdapterV2),
    the candidates it returns are then ranked into the top and remaining skills (see rank_skills).

    If a reranker is given, the best scoring candidates are reranked by an LLM, and the skills it picks are the
    top skills. If the reranker fails or picks nothing, the classifier ranking is kept.
    """

    def __init__(self, *,
                 version: ClassifierApiVersion,
                 client: ClassifierClient,
                 skill_search_service: Optional[SkillSearchService] = None,
                 occupation_skill_search_service: Optional[OccupationSkillSearchService] = None,
                 config: Optional[ClassifierSkillLinkerConfig] = None,
                 reranker: Optional[SkillReranker] = None,
                 overview_generator: Optional[ExperienceOverviewGenerator] = None):
        self._version = version
        self._config = config or ClassifierSkillLinkerConfig()
        self._reranker = reranker
        self._overview_generator = overview_generator
        self._occupation_skill_search_service = occupation_skill_search_service
        self._adapter = _create_adapter(version=version, client=client,
                                        skill_search_service=skill_search_service, config=self._config)
        self._logger = logging.getLogger(self.__class__.__name__)

    async def execute(self, *,
                      experience_title: str,
                      responsibilities: list[str],
                      company_name: Optional[str],
                      country_of_interest: Country,
                      work_type: WorkType,
                      location: Optional[str] = None,
                      timeline: Optional[Timeline] = None,
                      questions_and_answers: Optional[list[tuple[str, str]]] = None) -> SkillLinkerResponse:
        with traced_observation(
                name="classifier_skill_linker",
                as_type="chain",
                input={"experience_title": experience_title, "responsibilities": responsibilities},
                metadata={"version": self._version.value, "reranked": self._reranker is not None,
                          "with_overview": self._overview_generator is not None,
                          "with_occupation_expansion": self._occupation_skill_search_service is not None},
        ) as observation:
            overview_result = await self._generate_overview(
                experience_title=experience_title,
                company_name=company_name,
                work_type=work_type,
                location=location,
                timeline=timeline,
                country_of_interest=country_of_interest,
                responsibilities=responsibilities,
                questions_and_answers=questions_and_answers,
            )
            overview = overview_result.overview or None
            classifier_responsibilities = overview_result.professional_responsibilities or responsibilities
            llm_stats = overview_result.llm_stats
            try:
                matches = await self._adapter.classify(experience_title=experience_title,
                                                       responsibilities=classifier_responsibilities,
                                                       overview=overview)
            except ClassifierServiceError as e:
                # Do not break the conversation if the classifier is unavailable, behave like a linker that found nothing.
                self._logger.error("Failed to link skills for experience title: '%s'. Error: %s",
                                   experience_title, e, exc_info=e)
                return SkillLinkerResponse(top_skills=[], remaining_skills=[], llm_stats=llm_stats)

            occupation_skill_candidates = await self._expand_candidates_with_occupation_skills(
                matches.occupation_matches
            )
            all_candidates = [*matches.skill_candidates, *occupation_skill_candidates]

            top_skills, remaining_skills = rank_skills(all_candidates,
                                                       number_of_top_skills=self._config.number_of_top_skills)
            if self._reranker is not None and all_candidates:
                reranked = await self._rerank(experience_title=experience_title,
                                              responsibilities=responsibilities,
                                              company_name=company_name,
                                              work_type=work_type,
                                              candidates=all_candidates,
                                              overview=overview)
                if reranked is not None:
                    top_skills, remaining_skills = reranked
            response = SkillLinkerResponse(top_skills=top_skills,
                                           remaining_skills=remaining_skills,
                                           title_candidates=matches.title_candidates,
                                           llm_stats=llm_stats)
            update_observation(observation, output={
                "overview": overview,
                "professional_responsibilities": overview_result.professional_responsibilities,
                "occupation_expanded_candidates_count": len(occupation_skill_candidates),
                "top_skills": [skill.preferredLabel for skill in response.top_skills],
                "remaining_skills_count": len(response.remaining_skills),
            })
            if self._logger.isEnabledFor(logging.INFO):
                self._logger.info("Classifier (%s) linked experience '%s' to top skills: %s",
                                  self._version.value, experience_title,
                                  json.dumps([skill.preferredLabel for skill in response.top_skills], ensure_ascii=False))
            return response

    async def _generate_overview(self, *,
                                 experience_title: str,
                                 company_name: Optional[str],
                                 work_type: Optional[WorkType],
                                 location: Optional[str],
                                 timeline: Optional[Timeline],
                                 country_of_interest: Country,
                                 responsibilities: list[str],
                                 questions_and_answers: Optional[list[tuple[str, str]]]) -> ExperienceOverviewResult:
        if self._overview_generator is None:
            return ExperienceOverviewResult()
        try:
            return await self._overview_generator.execute(
                experience_title=experience_title,
                company_name=company_name,
                work_type=work_type,
                location=location,
                timeline=timeline,
                country_of_interest=country_of_interest,
                responsibilities=responsibilities,
                questions_and_answers=questions_and_answers,
            )
        except Exception as e:  # pylint: disable=broad-except
            self._logger.warning("Failed to generate experience overview for '%s', proceeding with responsibilities "
                                 "only. Error: %s", experience_title, e, exc_info=e)
            return ExperienceOverviewResult()

    async def _expand_candidates_with_occupation_skills(
            self,
            occupation_matches: list[OccupationMatch],
    ) -> list[SkillCandidate]:
        """
        Fetch associated taxonomy skills for the top classifier-matched occupations so the reranker always
        has a rich candidate pool. Essential skills are ordered before optional skills; all are marked
        is_best_match=False so unreranked ranking preserves direct classifier matches first.
        """
        if (self._occupation_skill_search_service is None
                or not occupation_matches
                or self._config.max_occupations_to_expand <= 0):
            return []

        top_occupations = occupation_matches[:self._config.max_occupations_to_expand]

        async def _lookup(occ: OccupationMatch) -> list[OccupationSkillEntity]:
            try:
                if occ.esco_code:
                    results = await self._occupation_skill_search_service.get_by_esco_code(code=occ.esco_code)
                    if results:
                        return results
                return await self._occupation_skill_search_service.search(query=occ.label, k=1)
            except Exception as e:  # pylint: disable=broad-except
                self._logger.warning(
                    "Failed to expand occupation '%s' (code=%s) into associated skills. Error: %s",
                    occ.label, occ.esco_code, e, exc_info=e
                )
                return []

        lookup_results = await asyncio.gather(*[_lookup(occ) for occ in top_occupations])

        essential_skills: list[AssociatedSkillEntity] = []
        other_skills: list[AssociatedSkillEntity] = []
        expanded_labels: list[str] = []
        for occ_entities in lookup_results:
            for occ_entity in occ_entities:
                expanded_labels.append(occ_entity.occupation.preferredLabel)
                for skill in occ_entity.associated_skills:
                    if skill.relationType == "essential":
                        essential_skills.append(skill)
                    else:
                        other_skills.append(skill)

        # Deduplicate while preserving essential-first, occupation-score ordering
        seen_uuids: set[str] = set()
        candidates: list[SkillCandidate] = []
        for skill in [*essential_skills, *other_skills]:
            if skill.UUID in seen_uuids:
                continue
            seen_uuids.add(skill.UUID)
            candidates.append(SkillCandidate(skill=skill, is_best_match=False))

        if self._logger.isEnabledFor(logging.INFO) and candidates:
            self._logger.info(
                "Expanded %d matched occupation(s) %s into %d associated skill candidates (%d essential)",
                len(expanded_labels),
                json.dumps(expanded_labels, ensure_ascii=False),
                len(candidates),
                len(essential_skills),
            )
        return candidates

    async def _rerank(self, *,
                      experience_title: str,
                      responsibilities: list[str],
                      company_name: Optional[str],
                      work_type: WorkType,
                      candidates: list[SkillCandidate],
                      overview: Optional[str] = None) -> Optional[tuple[list[SkillEntity], list[SkillEntity]]]:
        """
        Rerank the best scoring candidates with the LLM reranker.

        :return: (top_skills, remaining_skills), or None to keep the classifier ranking.
        """
        by_score = [candidate.skill for candidate in deduplicate_candidates(candidates)]
        try:
            top_skills = await self._reranker.rerank(experience_title=experience_title,
                                                     responsibilities=responsibilities,
                                                     company_name=company_name,
                                                     work_type=work_type,
                                                     candidates=by_score[:self._config.max_rerank_candidates],
                                                     max_skills=self._config.number_of_top_skills,
                                                     overview=overview)
        except LlmRerankerServiceError as e:
            # Do not break the conversation if the reranker is unavailable, keep the classifier ranking.
            self._logger.warning("Failed to rerank the skills of experience title: '%s', keeping the classifier "
                                 "ranking. Error: %s", experience_title, e, exc_info=e)
            return None
        if not top_skills:
            self._logger.warning("The reranker picked no skills for experience title: '%s', keeping the classifier "
                                 "ranking.", experience_title)
            return None
        top_skills_uuids = {skill.UUID for skill in top_skills}
        return top_skills, [skill for skill in by_score if skill.UUID not in top_skills_uuids]


def _create_adapter(*,
                    version: ClassifierApiVersion,
                    client: ClassifierClient,
                    skill_search_service: Optional[SkillSearchService],
                    config: ClassifierSkillLinkerConfig) -> IClassifierAdapter:
    if version == ClassifierApiVersion.V2:
        return ClassifierAdapterV2(client=client, config=config)
    if version == ClassifierApiVersion.V1:
        if skill_search_service is None:
            raise ValueError("The classifier v1 skill linker requires a skill search service to resolve the matched labels")
        return ClassifierAdapterV1(client=client, config=config, skill_search_service=skill_search_service)
    raise ValueError(f"ClassifierSkillLinker does not support the classifier API version: {version}")

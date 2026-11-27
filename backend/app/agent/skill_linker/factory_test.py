from unittest.mock import MagicMock

import pytest

from app.agent.skill_linker.classifier import ClassifierApiVersion
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2
from app.agent.skill_linker.classifier.linker import ClassifierSkillLinker
from app.agent.skill_linker.classifier.overview_generator import ExperienceOverviewGenerator
from app.agent.skill_linker.factory import get_skill_linker
from app.agent.skill_linker.llm_pipeline import ExperiencePipelineConfig, PipelineSkillLinker
from app.agent.skill_linker.config import SkillLinkerType
from app.app_config import ApplicationConfig


class TestGetSkillLinker:
    @pytest.mark.parametrize("skill_linker_type, expected_class", [
        (SkillLinkerType.LLM_PIPELINE, PipelineSkillLinker),
        (SkillLinkerType.CLASSIFIER, ClassifierSkillLinker),
    ])
    def test_returns_configured_linker(self, setup_application_config: ApplicationConfig,
                                       skill_linker_type: SkillLinkerType, expected_class: type):
        # GIVEN an application config with the given skill linker
        given_config = setup_application_config.model_copy(update={
            "skill_linker": skill_linker_type,
            "classifier_api_url": "https://classifier.test",
            "classifier_api_key": "key",
        })

        # WHEN the skill linker is created
        actual_linker = get_skill_linker(application_config=given_config,
                                         search_services=MagicMock(),
                                         experience_pipeline_config=ExperiencePipelineConfig())

        # THEN it is the expected implementation
        assert isinstance(actual_linker, expected_class)

    @pytest.mark.parametrize("classifier_api_version, expected_adapter_class", [
        (ClassifierApiVersion.V1, ClassifierAdapterV1),
        (ClassifierApiVersion.V2, ClassifierAdapterV2),
    ])
    def test_classifier_uses_configured_api_version(self, setup_application_config: ApplicationConfig,
                                                    classifier_api_version: ClassifierApiVersion,
                                                    expected_adapter_class: type):
        # GIVEN an application config with the classifier skill linker and the given classifier API version
        given_config = setup_application_config.model_copy(update={
            "skill_linker": SkillLinkerType.CLASSIFIER,
            "classifier_api_url": "https://classifier.test",
            "classifier_api_key": "key",
            "classifier_api_version": classifier_api_version,
        })

        # WHEN the skill linker is created
        actual_linker = get_skill_linker(application_config=given_config,
                                         search_services=MagicMock(),
                                         experience_pipeline_config=ExperiencePipelineConfig())

        # THEN the classifier linker uses the adapter of the configured API version
        assert isinstance(actual_linker, ClassifierSkillLinker)
        assert isinstance(actual_linker._adapter, expected_adapter_class)


    @pytest.mark.parametrize("number_of_clusters, number_of_top_skills_to_pick_per_cluster, expected_top_skills", [
        (5, 1, 5),
        (5, 2, 10),
        (3, 3, 9),
    ])
    def test_classifier_returns_as_many_top_skills_as_the_pipeline(self,
                                                                  setup_application_config: ApplicationConfig,
                                                                  number_of_clusters: int,
                                                                  number_of_top_skills_to_pick_per_cluster: int,
                                                                  expected_top_skills: int):
        # GIVEN an application config with the classifier skill linker
        given_config = setup_application_config.model_copy(update={
            "skill_linker": SkillLinkerType.CLASSIFIER,
            "classifier_api_url": "https://classifier.test",
            "classifier_api_key": "key",
        })
        # AND an experience pipeline config with the given clusters and top skills per cluster
        given_pipeline_config = ExperiencePipelineConfig(
            number_of_clusters=number_of_clusters,
            number_of_top_skills_to_pick_per_cluster=number_of_top_skills_to_pick_per_cluster)

        # WHEN the skill linker is created
        actual_linker = get_skill_linker(application_config=given_config,
                                         search_services=MagicMock(),
                                         experience_pipeline_config=given_pipeline_config)

        # THEN the classifier linker returns as many top skills as the pipeline would
        assert isinstance(actual_linker, ClassifierSkillLinker)
        assert actual_linker._config.number_of_top_skills == expected_top_skills

    @pytest.mark.parametrize("llm_reranker_url, expect_reranker", [
        (None, False),
        ("https://reranker.test", True),
    ])
    def test_classifier_reranks_only_when_reranker_url_is_set(self, setup_application_config: ApplicationConfig,
                                                              llm_reranker_url: str | None, expect_reranker: bool):
        # GIVEN an application config with the classifier skill linker, with or without an LLM reranker URL
        given_config = setup_application_config.model_copy(update={
            "skill_linker": SkillLinkerType.CLASSIFIER,
            "classifier_api_url": "https://classifier.test",
            "classifier_api_key": "key",
            "llm_reranker_url": llm_reranker_url,
        })

        # WHEN the skill linker is created
        actual_linker = get_skill_linker(application_config=given_config,
                                         search_services=MagicMock(),
                                         experience_pipeline_config=ExperiencePipelineConfig())

        # THEN the classifier linker has a reranker only if the URL is set
        assert isinstance(actual_linker, ClassifierSkillLinker)
        assert (actual_linker._reranker is not None) == expect_reranker

    def test_reranker_token_provider_is_shared_across_linkers(self, setup_application_config: ApplicationConfig):
        # GIVEN an application config with the classifier skill linker and an LLM reranker URL
        given_config = setup_application_config.model_copy(update={
            "skill_linker": SkillLinkerType.CLASSIFIER,
            "classifier_api_url": "https://classifier.test",
            "classifier_api_key": "key",
            "llm_reranker_url": "https://reranker.test",
        })

        # WHEN two skill linkers are created (one per request)
        actual_linkers = [get_skill_linker(application_config=given_config,
                                           search_services=MagicMock(),
                                           experience_pipeline_config=ExperiencePipelineConfig()) for _ in range(2)]

        # THEN they share the ID token provider, so the token is cached across requests
        actual_token_providers = [linker._reranker._client._token_provider for linker in actual_linkers]
        assert actual_token_providers[0] is actual_token_providers[1]

    def test_classifier_has_experience_overview_generator(self, setup_application_config: ApplicationConfig):
        # GIVEN an application config with the classifier skill linker
        given_config = setup_application_config.model_copy(update={
            "skill_linker": SkillLinkerType.CLASSIFIER,
            "classifier_api_url": "https://classifier.test",
            "classifier_api_key": "key",
        })

        # WHEN the skill linker is created
        given_search_services = MagicMock()
        actual_linker = get_skill_linker(application_config=given_config,
                                         search_services=given_search_services,
                                         experience_pipeline_config=ExperiencePipelineConfig())

        # THEN it is configured with an ExperienceOverviewGenerator and the occupation skill search service
        assert isinstance(actual_linker, ClassifierSkillLinker)
        assert isinstance(actual_linker._overview_generator, ExperienceOverviewGenerator)
        assert actual_linker._occupation_skill_search_service is given_search_services.occupation_skill_search_service


class TestApplicationConfig:
    def test_classifier_requires_url_and_key(self, setup_application_config: ApplicationConfig):
        # GIVEN a classifier skill linker without the classifier url and api key
        given_config = setup_application_config.model_dump()
        given_config.update(skill_linker=SkillLinkerType.CLASSIFIER, classifier_api_url=None, classifier_api_key=None)

        # WHEN the application config is validated
        # THEN a validation error is raised
        with pytest.raises(ValueError):
            ApplicationConfig.model_validate(given_config)

    def test_defaults_to_pipeline(self, setup_application_config: ApplicationConfig):
        # GIVEN an application config without a skill linker
        given_config = setup_application_config.model_dump(exclude={"skill_linker"})

        # WHEN the application config is validated
        actual_config = ApplicationConfig.model_validate(given_config)

        # THEN the linking and ranking pipeline is used
        assert actual_config.skill_linker == SkillLinkerType.LLM_PIPELINE

    def test_defaults_classifier_api_version_to_v2(self, setup_application_config: ApplicationConfig):
        # GIVEN a classifier skill linker without a classifier API version
        given_config = setup_application_config.model_dump(exclude={"classifier_api_version"})
        given_config.update(skill_linker=SkillLinkerType.CLASSIFIER, classifier_api_url="https://classifier.test",
                            classifier_api_key="key")

        # WHEN the application config is validated
        actual_config = ApplicationConfig.model_validate(given_config)

        # THEN the v2 classifier API is used
        assert actual_config.classifier_api_version == ClassifierApiVersion.V2

    def test_parses_env_values(self, setup_application_config: ApplicationConfig):
        # GIVEN the skill linker and the classifier API version as raw environment variable values
        given_config = setup_application_config.model_dump()
        given_config.update(skill_linker="classifier", classifier_api_version="v1",
                            classifier_api_url="https://classifier.test", classifier_api_key="key")

        # WHEN the application config is validated
        actual_config = ApplicationConfig.model_validate(given_config)

        # THEN they are parsed to the enums
        assert actual_config.skill_linker == SkillLinkerType.CLASSIFIER
        assert actual_config.classifier_api_version == ClassifierApiVersion.V1

    @pytest.mark.parametrize("given_skill_linker", ["linking_and_ranking_pipeline", "classifier_v1", "classifier_v2"])
    def test_rejects_removed_skill_linker_values(self, setup_application_config: ApplicationConfig,
                                                 given_skill_linker: str):
        # GIVEN a skill linker value that is no longer supported
        # (the pipeline was renamed to llm_pipeline, the classifier API version moved to CLASSIFIER_API_VERSION)
        given_config = setup_application_config.model_dump()
        given_config.update(skill_linker=given_skill_linker, classifier_api_url="https://classifier.test",
                            classifier_api_key="key")

        # WHEN the application config is validated
        # THEN a validation error is raised
        with pytest.raises(ValueError):
            ApplicationConfig.model_validate(given_config)

from unittest.mock import MagicMock

import pytest

from app.agent.skill_linker.classifier import ClassifierApiVersion
from app.agent.skill_linker.classifier.adapters import ClassifierAdapterV1, ClassifierAdapterV2
from app.agent.skill_linker.classifier.linker import ClassifierSkillLinker
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

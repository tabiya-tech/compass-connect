from unittest.mock import MagicMock

import pytest

from app.agent.skill_linker.classifier.classifier_skill_linker import ClassifierSkillLinker
from app.agent.skill_linker.get_skill_linker import get_skill_linker
from app.agent.skill_linker.linking_and_ranking_pipeline import ExperiencePipelineConfig
from app.agent.skill_linker.pipeline_skill_linker import PipelineSkillLinker
from app.agent.skill_linker.skill_linker_type import SkillLinkerType
from app.app_config import ApplicationConfig


class TestGetSkillLinker:
    @pytest.mark.parametrize("skill_linker_type, expected_class", [
        (SkillLinkerType.LINKING_AND_RANKING_PIPELINE, PipelineSkillLinker),
        (SkillLinkerType.CLASSIFIER_V1, ClassifierSkillLinker),
        (SkillLinkerType.CLASSIFIER_V2, ClassifierSkillLinker),
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


class TestApplicationConfig:
    @pytest.mark.parametrize("skill_linker_type", [SkillLinkerType.CLASSIFIER_V1, SkillLinkerType.CLASSIFIER_V2])
    def test_classifier_requires_url_and_key(self, setup_application_config: ApplicationConfig,
                                             skill_linker_type: SkillLinkerType):
        # GIVEN a classifier skill linker without the classifier url and api key
        given_config = setup_application_config.model_dump()
        given_config.update(skill_linker=skill_linker_type, classifier_api_url=None, classifier_api_key=None)

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
        assert actual_config.skill_linker == SkillLinkerType.LINKING_AND_RANKING_PIPELINE

    def test_parses_env_value(self, setup_application_config: ApplicationConfig):
        # GIVEN the skill linker as a raw environment variable value
        given_config = setup_application_config.model_dump()
        given_config.update(skill_linker="classifier_v2", classifier_api_url="https://classifier.test",
                            classifier_api_key="key")

        # WHEN the application config is validated
        actual_config = ApplicationConfig.model_validate(given_config)

        # THEN it is parsed to the enum
        assert actual_config.skill_linker == SkillLinkerType.CLASSIFIER_V2

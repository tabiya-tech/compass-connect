import logging

import pytest

from app.agent.skill_linker.llm_pipeline import ExperiencePipelineConfig
from app.app_config import ApplicationConfig


class TestExperiencePipelineConfigFromApplicationConfig:
    def test_loads_the_given_counts(self, setup_application_config: ApplicationConfig):
        # GIVEN an application config with positive pipeline counts
        given_pipeline_config = {"number_of_clusters": 3, "number_of_top_skills_to_pick_per_cluster": 2}
        given_config = setup_application_config.model_copy(update={"experience_pipeline_config": given_pipeline_config})

        # WHEN the experience pipeline config is loaded
        actual_config = ExperiencePipelineConfig.from_application_config(application_config=given_config,
                                                                         logger=logging.getLogger())

        # THEN the given counts are used
        assert actual_config.number_of_clusters == given_pipeline_config["number_of_clusters"]
        assert (actual_config.number_of_top_skills_to_pick_per_cluster
                == given_pipeline_config["number_of_top_skills_to_pick_per_cluster"])

    @pytest.mark.parametrize("given_pipeline_config", [
        {"number_of_clusters": 0},
        {"number_of_clusters": -5},
        {"number_of_top_skills_to_pick_per_cluster": 0},
        {"number_of_top_skills_to_pick_per_cluster": -1},
        {"number_of_clusters": -5, "number_of_top_skills_to_pick_per_cluster": -1},
    ])
    def test_falls_back_to_the_default_config_for_nonpositive_counts(self,
                                                                     setup_application_config: ApplicationConfig,
                                                                     given_pipeline_config: dict[str, int]):
        # GIVEN an application config with a nonpositive pipeline count
        given_config = setup_application_config.model_copy(update={"experience_pipeline_config": given_pipeline_config})

        # WHEN the experience pipeline config is loaded
        actual_config = ExperiencePipelineConfig.from_application_config(application_config=given_config,
                                                                         logger=logging.getLogger())

        # THEN the default config is used
        assert actual_config == ExperiencePipelineConfig()

from logging import Logger

from pydantic import BaseModel, ConfigDict

from app.app_config import ApplicationConfig


class ExperiencePipelineConfig(BaseModel):
    number_of_clusters: int = 5
    """
    Default is 5
    
    The number of clusters to group the responsibilities. 
    Each cluster of responsibilities will contribute to N top skills (where N = number_of_top_skills_to_pick_per_cluster).
    """

    number_of_top_skills_to_pick_per_cluster: int = 1
    """
    Default is 1
    The number of top skills to pick for each cluster among the top skills candidates of the cluster.
    """

    top_skills_threshold: int = 7
    """
    Default is 7
    When scoring the top skills of each cluster, the top skills with a score lower than this threshold will be ignored.
    See PickTopSkillsTool for more details.
    """

    number_of_occupation_alt_titles: int = 5
    """
    Default is 5 
    The number of alternative titles to infer from the experience title, company, work type and responsibilities and country of interest
    Each alternative title will be linked to a set of occupations.
    """

    number_of_occupations_per_cluster: int = 15
    """
    Default is 15
    The number of The number of most relevant occupations chosen from all the occupation candidates that where linked to each alternative title.
    This is the number of occupations that will be used by the skill linking tool to find the top skills for each cluster. 
    """

    number_of_occupations_candidates_per_title: int = 30
    """
    Default is 30
    The number of occupation candidates to consider for each alternative title. 
    This refers to the number of occupations retrieved from the search service for each alternative title.
    """

    number_of_top_skills_candidates_per_cluster: int = 5
    """
    Default is 5
    The number of top skills candidates to return for each cluster.
    It also corresponds to the number of skills selected from each responsibility among all the skill candidates returned by the search service.
    """

    number_of_skill_candidates_per_responsibility: int = 15
    """
    Default is 15
    The number of skill candidates to consider for each responsibility.
    These are the number of skills that are retrieved from the search service for each responsibility.
    """

    only_essential_skills: bool = True
    """
    Default is True
    If True, only the essential skills will be considered when linking the responsibilities to the skills.
    This applies to the skills associated with esco occupations.
    """

    only_high_signal_skills: bool = True
    """
    Default is True
    If True, only skills with "high" signaling values will be considered when linking the responsibilities to the skills.
    This applies to the skills associated with icatus occupations.
    """

    ignore_occupations: bool = False
    """
    Default is False
    If True, the skills search will consider all the skills in the ESCO database and will not be limited 
    to the skills associated with the occupations found."
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    @staticmethod
    def from_application_config(*,
                                application_config: ApplicationConfig,
                                logger: Logger) -> "ExperiencePipelineConfig":
        if application_config is None or application_config.experience_pipeline_config is None:
            logger.warning("No experience pipeline config found in the application config. Using default config.")
            return ExperiencePipelineConfig()

        # merge the application config with the default config
        try:
            return ExperiencePipelineConfig.model_validate(application_config.experience_pipeline_config)
        except Exception as e:
            logger.error("Falling back to the default experience pipeline config due to an error: %s", e)
            return ExperiencePipelineConfig()

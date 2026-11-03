from app.agent.skill_linker.llm_pipeline.tools.relevance_ranker import EntityRelevanceRanker, EntityRelevanceRankerOutput
from app.vector_search.esco_entities import SkillEntity


class _SkillRanker(EntityRelevanceRanker[SkillEntity]):
    def __init__(self):
        super().__init__(entity_type='skill')

    async def execute(
            self,
            *,
            job_titles: list[str],
            responsibilities: list[str],
            skills: list[SkillEntity],
            top_k: int = 5
    ) -> EntityRelevanceRankerOutput[SkillEntity]:
        """
        Given
        - a list of job titles,
        - a list of responsibilities,
        - and a list of skills
        rank the skills into:
        - top_k most relevant skills
        - remaining skills
        """
        return await super().execute(
            job_titles=job_titles,
            responsibilities=responsibilities,
            entities_to_rank=skills,
            top_k=top_k
        )

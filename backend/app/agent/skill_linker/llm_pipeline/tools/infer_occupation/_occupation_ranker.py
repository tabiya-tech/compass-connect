from app.agent.skill_linker.llm_pipeline.tools.relevance_ranker import EntityRelevanceRanker, EntityRelevanceRankerOutput
from app.vector_search.esco_entities import OccupationEntity


class _OccupationRanker(EntityRelevanceRanker[OccupationEntity]):
    def __init__(self):
        super().__init__(entity_type='occupation')

    async def execute(
            self,
            *,
            job_titles: list[str],
            responsibilities: list[str],
            occupations: list[OccupationEntity],
            top_k: int = 5
    ) -> EntityRelevanceRankerOutput[OccupationEntity]:
        """
        Given
        - a list of job titles,
        - a list of responsibilities,
        - and a list of occupations
        rank the occupations into:
        - top_k most relevant occupations
        - remaining occupations
        """
        return await super().execute(
            job_titles=job_titles,
            responsibilities=responsibilities,
            entities_to_rank=occupations,
            top_k=top_k
        )

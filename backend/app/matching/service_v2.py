from typing import Optional

from app.matching.client import MatchingServiceClient
from app.matching.service import MatchingService
from app.matching.matching_types import (
    SkillsVector,
    PreferenceVector,
    CompassMatchingResult,
    MatchingAlgorithmVersion,
    MatchingRequest,
)
# The v2 endpoint now returns the same shape as /match, so reuse v1's response models and
# mappers as the single source of truth (re-exported here so callers/tests can import them).
from app.matching.service_v1 import (
    _ResponseList,
    _to_compass_occupation,
    _to_compass_opportunity,
    _to_compass_skill_gap,
)

__all__ = ["MatchingServiceV2", "_ResponseList"]

_MATCH_V2_PATH = "/experiments/v2/match"


class MatchingServiceV2(MatchingService):
    def __init__(self, client: MatchingServiceClient):
        self._client = client

    @property
    def algorithm_version(self) -> MatchingAlgorithmVersion:
        return "v2"

    async def generate_recommendations(self,
                                       youth_id: str,
                                       city: Optional[str],
                                       province: Optional[str],
                                       skills_vector: SkillsVector,
                                       preference_vector: PreferenceVector) -> CompassMatchingResult:
        request = MatchingRequest(
            user_id=youth_id,
            city=city or "",
            province=province or "",
            skills_vector=skills_vector,
            preference_vector=preference_vector,
        )

        response = await self._client.process_request(_ResponseList, _MATCH_V2_PATH, request)
        if not response.root:
            return CompassMatchingResult(user_id=youth_id, algorithm_version="v2")

        first = response.root[0]
        return CompassMatchingResult(
            user_id=first.user_id or youth_id,
            algorithm_version="v2",
            occupations=[_to_compass_occupation(o) for o in first.occupation_recommendations],
            opportunities=[_to_compass_opportunity(o) for o in first.opportunity_recommendations],
            skill_gaps=[_to_compass_skill_gap(g) for g in first.skill_gap_recommendations],
        )

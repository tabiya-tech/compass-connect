from app.agent.skill_linker.classifier.skill_ranking import SkillCandidate, rank_skills
from app.vector_search.esco_entities import SkillEntity


def _candidate(uuid: str, score: float, is_best_match: bool) -> SkillCandidate:
    return SkillCandidate(skill=SkillEntity(id="", UUID=uuid, preferredLabel=uuid, altLabels=[], description="",
                                            skillType="knowledge", score=score),
                          is_best_match=is_best_match)


class TestRankSkills:
    def test_top_skills_are_the_best_matches_sorted_by_score(self):
        # GIVEN two best match candidates and one other candidate
        given_candidates = [_candidate("a", 0.5, True), _candidate("b", 0.9, True), _candidate("c", 0.8, False)]

        # WHEN the candidates are ranked
        actual_top_skills, actual_remaining_skills = rank_skills(given_candidates, number_of_top_skills=5)

        # THEN the top skills are the best matches, sorted by score
        assert [skill.UUID for skill in actual_top_skills] == ["b", "a"]
        # AND the other candidate is a remaining skill
        assert [skill.UUID for skill in actual_remaining_skills] == ["c"]

    def test_deduplicates_by_uuid(self):
        # GIVEN the same skill as a low scoring best match and as a high scoring other match
        given_candidates = [_candidate("x", 0.4, True), _candidate("x", 0.7, False)]

        # WHEN the candidates are ranked
        actual_top_skills, actual_remaining_skills = rank_skills(given_candidates, number_of_top_skills=5)

        # THEN the skill is returned once, as a top skill, with the highest score
        assert [(skill.UUID, skill.score) for skill in actual_top_skills] == [("x", 0.7)]
        assert actual_remaining_skills == []

    def test_best_matches_over_the_limit_are_remaining_skills(self):
        # GIVEN three best match candidates and a higher scoring other candidate
        given_candidates = [_candidate("a", 0.9, True), _candidate("b", 0.8, True), _candidate("c", 0.7, True),
                            _candidate("d", 0.95, False)]

        # WHEN the candidates are ranked keeping 2 top skills
        actual_top_skills, actual_remaining_skills = rank_skills(given_candidates, number_of_top_skills=2)

        # THEN the 2 best scoring best matches are the top skills
        assert [skill.UUID for skill in actual_top_skills] == ["a", "b"]
        # AND every other skill is a remaining skill, sorted by score
        assert [skill.UUID for skill in actual_remaining_skills] == ["d", "c"]

    def test_no_candidates(self):
        # GIVEN no candidates
        # WHEN they are ranked
        actual_top_skills, actual_remaining_skills = rank_skills([], number_of_top_skills=5)

        # THEN no skills are returned
        assert actual_top_skills == []
        assert actual_remaining_skills == []

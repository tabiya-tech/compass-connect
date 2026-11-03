from pydantic import BaseModel

from app.vector_search.esco_entities import SkillEntity


class SkillCandidate(BaseModel):
    """
    A taxonomy skill matched by the classifier for one of the extracted entities.
    """

    skill: SkillEntity

    is_best_match: bool
    """
    Whether the skill was the best match for one of the extracted entities.
    """


def rank_skills(candidates: list[SkillCandidate], *,
                number_of_top_skills: int) -> tuple[list[SkillEntity], list[SkillEntity]]:
    """
    Rank the skill candidates into the top skills and the remaining skills of the experience.

    The candidates are deduplicated by UUID, keeping the highest score. A skill is a top skill candidate
    if it was the best match of at least one extracted entity. The best scoring top skill candidates
    are the top skills, every other skill is a remaining skill. Both lists are sorted by score, descending.

    :return: (top_skills, remaining_skills)
    """
    best_by_uuid: dict[str, SkillCandidate] = {}
    for candidate in candidates:
        existing = best_by_uuid.get(candidate.skill.UUID)
        if existing is None:
            best_by_uuid[candidate.skill.UUID] = candidate
            continue
        best_by_uuid[candidate.skill.UUID] = SkillCandidate(
            skill=candidate.skill if candidate.skill.score > existing.skill.score else existing.skill,
            is_best_match=candidate.is_best_match or existing.is_best_match
        )

    by_score = sorted(best_by_uuid.values(), key=lambda c: c.skill.score, reverse=True)
    top_skill_candidates = [c.skill for c in by_score if c.is_best_match]
    top_skills = top_skill_candidates[:number_of_top_skills]
    top_skills_uuids = {skill.UUID for skill in top_skills}
    remaining_skills = [c.skill for c in by_score if c.skill.UUID not in top_skills_uuids]
    return top_skills, remaining_skills

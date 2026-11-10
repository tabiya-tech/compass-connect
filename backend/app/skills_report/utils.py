"""
Port of `frontend-new/src/experiences/report/util.ts` (and the small helpers of the report components).
"""
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from app.skills_report.types import ReportExperience, ReportSkill, ReportWorkType

# Colours used by the report (frontend: COLORS in util.ts and TabiyaBasicColors in applicationTheme.ts)
COLOR_TEXT_BLACK = "#000000"
COLOR_GREY_700 = "#605E5B"
COLOR_DARK_BLUE = "#002147"
COLOR_GRAY_DARK = "#41403D"
COLOR_SKILL_TEXT = "#211F1D"

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December"]


def _locale_compare_key(value: str) -> tuple:
    """
    Approximation of JavaScript's `String.prototype.localeCompare` (ICU root collation) for sorting:
    letters compare case- and accent-insensitively first, then accents decide, then lowercase sorts before uppercase.
    """
    decomposed = unicodedata.normalize("NFD", value)
    base = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    accents = tuple(unicodedata.combining(c) for c in decomposed)
    case = tuple(0 if c.islower() or not c.isalpha() else 1 for c in value)
    return base, accents, case


def get_unique_skills(experiences: list[ReportExperience]) -> list[ReportSkill]:
    """All unique skills (by preferred label) of the experiences, sorted alphabetically."""
    skills: list[ReportSkill] = []
    seen_labels: set[str] = set()
    for experience in experiences:
        for skill in experience.top_skills:
            if skill.preferred_label not in seen_labels:
                seen_labels.add(skill.preferred_label)
                skills.append(skill)
    return sorted(skills, key=lambda s: _locale_compare_key(s.preferred_label))


def format_date(date_string: Optional[str], now: Optional[datetime] = None) -> str:
    """Format a date as 'Month DD, YYYY' (UTC, English month names), like the frontend `formatDate`."""
    if date_string:
        value = date_string.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        date = datetime.fromisoformat(value)
        if date.tzinfo is None:
            # JS parses date-only strings as UTC and date-time strings without offset as local time;
            # the backend has no "local time" for the user, UTC is used for both.
            date = date.replace(tzinfo=timezone.utc)
        date = date.astimezone(timezone.utc)
    else:
        date = now or datetime.now(timezone.utc)
    return f"{_MONTH_NAMES[date.month - 1]} {date.day:02d}, {date.year}"


def group_experiences_by_work_type(experiences: list[ReportExperience]) -> dict[str, list[ReportExperience]]:
    return {
        "salary_work": [e for e in experiences if e.work_type == ReportWorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT],
        "unpaid_work": [e for e in experiences if e.work_type == ReportWorkType.UNSEEN_UNPAID],
        "trainee_work": [e for e in experiences if e.work_type == ReportWorkType.FORMAL_SECTOR_UNPAID_TRAINEE_WORK],
        "uncategorized": [e for e in experiences if e.work_type is None],
    }


def prettify_text(text: str) -> str:
    return " ".join(line.strip() for line in text.split("\n"))


def capitalize_first_letter(value: str) -> str:
    return value[:1].upper() + value[1:]


def get_display_title(experience: ReportExperience) -> str:
    # JS: normalized_experience_title ?? experience_title
    return experience.normalized_experience_title if experience.normalized_experience_title is not None \
        else experience.experience_title


def get_date_range_text(experience: ReportExperience) -> str:
    start = experience.timeline.start
    end = experience.timeline.end
    if end and start:
        return f"{start} — {end}"
    return start or end or ""


def get_education_text(program: str, school: str) -> str:
    return " · ".join(value for value in [program, school] if value)

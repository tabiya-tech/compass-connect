from datetime import datetime, timezone

import pytest

from app.skills_report.types import ReportExperience, ReportWorkType, merge_skills_report_config
from app.skills_report.utils import (capitalize_first_letter, format_date, get_date_range_text, get_display_title,
                                     get_education_text, get_unique_skills, group_experiences_by_work_type,
                                     prettify_text)


def _skill(uuid: str, label: str) -> dict:
    return {"UUID": uuid, "preferredLabel": label, "description": f"{label} description"}


def _experience(uuid: str, work_type=None, skills=None, **kwargs) -> ReportExperience:
    return ReportExperience.model_validate({"UUID": uuid, "work_type": work_type, "top_skills": skills or [], **kwargs})


class TestFormatDate:
    @pytest.mark.parametrize("given_date, expected", [
        ("2025-03-14T09:30:00Z", "March 14, 2025"),
        ("2024-12-31T23:59:59Z", "December 31, 2024"),
        ("2025-01-05", "January 05, 2025"),
        # converted to UTC like the frontend
        ("2022-02-03T01:05:06+03:00", "February 02, 2022"),
    ])
    def test_formats_the_date_in_utc_with_english_month_names(self, given_date, expected):
        # GIVEN a conversation date
        # WHEN it is formatted
        actual = format_date(given_date)
        # THEN it is formatted as "Month DD, YYYY" in UTC
        assert actual == expected

    def test_uses_the_current_date_when_no_date_is_given(self):
        # GIVEN no conversation date
        # AND a current date
        given_now = datetime(2026, 7, 4, tzinfo=timezone.utc)
        # WHEN the date is formatted
        actual = format_date(None, now=given_now)
        # THEN the current date is used
        assert actual == "July 04, 2026"


class TestGetUniqueSkills:
    def test_returns_unique_skills_by_label_sorted_like_locale_compare(self):
        # GIVEN experiences with duplicated, accented and mixed-case skill labels
        given_experiences = [
            _experience("1", skills=[_skill("a", "Zapatería"), _skill("b", "árbol"), _skill("c", "año")]),
            _experience("2", skills=[_skill("d", "árbol"), _skill("e", "Ética"), _skill("f", "edición"),
                                     _skill("g", "ana")]),
        ]
        # WHEN the unique skills are computed
        actual = get_unique_skills(given_experiences)
        # THEN every label appears once (the first occurrence is kept)
        assert [s.uuid for s in actual if s.preferred_label == "árbol"] == ["b"]
        # AND the labels are sorted case and accent insensitively (like JavaScript's localeCompare)
        assert [s.preferred_label for s in actual] == ["ana", "año", "árbol", "edición", "Ética", "Zapatería"]


class TestGroupExperiencesByWorkType:
    def test_groups_the_experiences_and_ignores_self_employment(self):
        # GIVEN experiences of every work type
        given_experiences = [
            _experience("salary", ReportWorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT),
            _experience("unpaid", ReportWorkType.UNSEEN_UNPAID),
            _experience("trainee", ReportWorkType.FORMAL_SECTOR_UNPAID_TRAINEE_WORK),
            _experience("none", None),
            _experience("self", ReportWorkType.SELF_EMPLOYMENT),
        ]
        # WHEN they are grouped
        actual = group_experiences_by_work_type(given_experiences)
        # THEN each group contains the experiences of its work type
        assert {k: [e.uuid for e in v] for k, v in actual.items()} == {
            "salary_work": ["salary"], "unpaid_work": ["unpaid"], "trainee_work": ["trainee"],
            "uncategorized": ["none"]}


class TestExperienceTexts:
    @pytest.mark.parametrize("start, end, expected", [
        ("2019", "2022", "2019 — 2022"),
        ("2019", "", "2019"),
        ("", "2022", "2022"),
        ("", "", ""),
    ])
    def test_date_range(self, start, end, expected):
        # GIVEN an experience with a timeline
        given_experience = _experience("1", timeline={"start": start, "end": end})
        # WHEN the date range text is computed
        # THEN it is the expected text
        assert get_date_range_text(given_experience) == expected

    def test_display_title_prefers_the_normalized_title_even_when_empty(self):
        # GIVEN an experience with an empty normalized title (JS: normalized ?? title)
        given_experience = _experience("1", experience_title="Shop work", normalized_experience_title="")
        # WHEN the display title is computed
        # THEN the normalized title is used
        assert get_display_title(given_experience) == ""
        # AND without a normalized title, the title is used
        assert get_display_title(_experience("2", experience_title="Shop work")) == "Shop work"

    def test_education_text_and_text_helpers(self):
        # GIVEN/WHEN/THEN the education text joins the program and the school that are present
        assert get_education_text("BSc", "UoN") == "BSc · UoN"
        assert get_education_text("", "UoN") == "UoN"
        # AND multi line texts are joined into a single line
        assert prettify_text("  a\n  b  \nc") == "a b c"
        # AND the first letter is capitalized
        assert capitalize_first_letter("assist customers") == "Assist customers"
        assert capitalize_first_letter("") == ""


class TestMergeSkillsReportConfig:
    def test_deep_merges_the_override_with_the_defaults(self):
        # GIVEN a partial config override
        given_override = {"logos": [], "report": {"experienceDetails": {"companyName": False}}}
        # WHEN it is merged with the defaults
        actual = merge_skills_report_config(given_override)
        # THEN the overridden values are used
        assert actual.logos == []
        assert actual.report.experience_details.company_name is False
        # AND the other values keep their defaults
        assert actual.report.experience_details.title is True
        assert actual.report.summary.show is True

    def test_uses_the_default_logo_without_override(self):
        # WHEN the config is merged without override
        actual = merge_skills_report_config(None)
        # THEN the default logo is used
        assert [logo.url for logo in actual.logos] == ["/njila-logo-dark.svg"]

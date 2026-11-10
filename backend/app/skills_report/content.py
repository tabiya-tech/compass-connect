"""
The report texts (port of `frontend-new/src/experiences/report/reportContent.ts`).

Translations live in `app/i18n/locales/<locale>/skills_report.json` (copied from the frontend `experiences.report.*`
keys, with `{{name}}` placeholders converted to `{name}`).
"""
from dataclasses import dataclass

from app.i18n.translation_service import get_i18n_manager
from app.i18n.types import Locale

_DOMAIN = "skills_report"


@dataclass(frozen=True)
class ReportContent:
    locale: Locale
    app_name: str

    def _t(self, key: str, **kwargs) -> str:
        raw = get_i18n_manager().get_translation(self.locale, _DOMAIN, key, fallback_message=key)
        try:
            return raw.format(**kwargs)
        except (KeyError, IndexError):
            return raw

    @property
    def skills_report_title(self) -> str:
        return self._t("skillsReportTitle")

    @property
    def skills_description_title(self) -> str:
        return self._t("skillsDescriptionTitle")

    @property
    def experiences_title(self) -> str:
        return self._t("experiencesTitle")

    @property
    def self_employment_title(self) -> str:
        return self._t("selfEmploymentTitle")

    @property
    def salary_work_title(self) -> str:
        return self._t("salaryWorkTitle")

    @property
    def unpaid_work_title(self) -> str:
        return self._t("unpaidWorkTitle")

    @property
    def trainee_work_title(self) -> str:
        return self._t("traineeWorkTitle")

    @property
    def uncategorized_title(self) -> str:
        return self._t("uncategorizedTitle")

    @property
    def top_skills_title(self) -> str:
        return self._t("topSkillsTitle")

    @property
    def skills_description_text(self) -> str:
        return self._t("skillsDescriptionText", appName=self.app_name)

    @property
    def disclaimer_text_part1(self) -> str:
        return self._t("disclaimer.part1")

    @property
    def disclaimer_text_part2(self) -> str:
        return self._t("disclaimer.part2")

    @property
    def disclaimer_text_part3(self) -> str:
        return self._t("disclaimer.part3", appName=self.app_name)

    def report_body_text(self, current_date: str) -> str:
        return self._t("bodyText", date=current_date, appName=self.app_name)

from typing import Optional

from app.i18n.types import Locale
from app.skills_report.content import ReportContent
from app.skills_report.types import SkillsReportData, SkillsReportOutputConfig


def _content(locale: Locale, app_name: str) -> ReportContent:
    return ReportContent(locale=locale, app_name=app_name)


def generate_skills_report_pdf(data: SkillsReportData, *, locale: Locale, app_name: str,
                               config: Optional[SkillsReportOutputConfig] = None) -> bytes:
    """Generate the skills report as PDF bytes (same layout as the frontend react-pdf report)."""
    from app.skills_report.pdf import generate_skills_report_pdf as _generate
    return _generate(data, config or SkillsReportOutputConfig(), _content(locale, app_name))


def generate_skills_report_docx(data: SkillsReportData, *, locale: Locale, app_name: str,
                                config: Optional[SkillsReportOutputConfig] = None) -> bytes:
    """Generate the skills report as DOCX bytes (same structure as the frontend docx.js report)."""
    from app.skills_report.docx import generate_skills_report_docx as _generate
    return _generate(data, config or SkillsReportOutputConfig(), _content(locale, app_name))

"""
Input models of the skills report.

They mirror the frontend types (`frontend-new/src/experiences/report/types.ts`,
`frontend-new/src/experiences/experienceService/experiences.types.ts` and
`frontend-new/src/experiences/report/config/types.ts`). The aliases use the frontend (JSON) field names so that the
same payload/fixtures can be used by the frontend and the backend.
"""
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ReportWorkType(str, Enum):
    FORMAL_SECTOR_WAGED_EMPLOYMENT = "FORMAL_SECTOR_WAGED_EMPLOYMENT"
    FORMAL_SECTOR_UNPAID_TRAINEE_WORK = "FORMAL_SECTOR_UNPAID_TRAINEE_WORK"
    UNSEEN_UNPAID = "UNSEEN_UNPAID"
    # The frontend Experience type has no SELF_EMPLOYMENT value, experiences with this work type are not listed
    SELF_EMPLOYMENT = "SELF_EMPLOYMENT"


class ReportSkill(_Model):
    uuid: str = Field(alias="UUID")
    preferred_label: str = Field(alias="preferredLabel")
    description: str = ""
    alt_labels: list[str] = Field(default_factory=list, alias="altLabels")
    order_index: int = Field(default=0, alias="orderIndex")


class ReportTimeline(_Model):
    start: Optional[str] = ""
    end: Optional[str] = ""


class ReportExperience(_Model):
    uuid: str = Field(alias="UUID")
    timeline: ReportTimeline = Field(default_factory=ReportTimeline)
    experience_title: str = ""
    normalized_experience_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    work_type: Optional[ReportWorkType] = None
    top_skills: list[ReportSkill] = Field(default_factory=list)
    remaining_skills: list[ReportSkill] = Field(default_factory=list)
    summary: Optional[str] = None
    exploration_phase: Optional[str] = None


class SkillsReportData(_Model):
    """The personal information and experiences rendered in the report (frontend `ReportProps`)."""
    name: str = ""
    email: str = ""
    location: str = ""
    school: str = ""
    program: str = ""
    experiences: list[ReportExperience] = Field(default_factory=list)
    conversation_conducted_at: Optional[str] = Field(default=None, alias="conversationConductedAt")


class LogoDocxStyles(_Model):
    width: float
    height: float


class LogoItem(_Model):
    url: str
    docx_styles: LogoDocxStyles = Field(alias="docxStyles")
    # react-pdf style object of the logo <Image>; the backend supports width, height and the padding/margin keys
    pdf_styles: dict[str, Any] = Field(default_factory=dict, alias="pdfStyles")


class DownloadFormat(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"


class ReportSummaryConfig(_Model):
    show: bool = True


class ReportExperienceDetailsConfig(_Model):
    title: bool = True
    summary: bool = True
    location: bool = True
    date_range: bool = Field(default=True, alias="dateRange")
    company_name: bool = Field(default=True, alias="companyName")


class ReportConfig(_Model):
    summary: ReportSummaryConfig = Field(default_factory=ReportSummaryConfig)
    experience_details: ReportExperienceDetailsConfig = Field(default_factory=ReportExperienceDetailsConfig,
                                                              alias="experienceDetails")


DEFAULT_LOGOS: list[dict] = [
    {"url": "/njila-logo-dark.svg", "docxStyles": {"width": 120, "height": 62}, "pdfStyles": {"height": 46}},
]


class SkillsReportOutputConfig(_Model):
    logos: list[LogoItem] = Field(default_factory=lambda: [LogoItem.model_validate(logo) for logo in DEFAULT_LOGOS])
    download_formats: list[DownloadFormat] = Field(default_factory=lambda: [DownloadFormat.DOCX, DownloadFormat.PDF],
                                                   alias="downloadFormats")
    report: ReportConfig = Field(default_factory=ReportConfig)


def merge_skills_report_config(override: Optional[dict] = None) -> SkillsReportOutputConfig:
    """
    Port of the frontend `mergeSkillsReportConfig`: deep merges a (partial) config override with the defaults.
    """
    override = override or {}
    report_override = override.get("report") or {}
    merged = {
        "logos": override["logos"] if override.get("logos") is not None else DEFAULT_LOGOS,
        "downloadFormats": override["downloadFormats"] if override.get("downloadFormats") is not None
        else [DownloadFormat.DOCX.value, DownloadFormat.PDF.value],
        "report": {
            "summary": {"show": True, **(report_override.get("summary") or {})},
            "experienceDetails": {"title": True, "summary": True, "location": True, "dateRange": True,
                                  "companyName": True, **(report_override.get("experienceDetails") or {})},
        },
    }
    return SkillsReportOutputConfig.model_validate(merged)

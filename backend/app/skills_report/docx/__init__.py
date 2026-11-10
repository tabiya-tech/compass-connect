"""
The skills report DOCX, generated with python-docx.

This is a 1:1 mirror of the frontend docx.js document (keep them in sync!):
  - frontend-new/src/experiences/report/reportDocx/constructSkillReportDocument.ts
  - frontend-new/src/experiences/report/reportDocx/components/**

The paragraphs, runs and their properties are written exactly as docx.js writes them (including explicit
`keepNext=false`, the `start` alignment and the docx.js default styles in `styles.xml`).
"""
import io
from pathlib import Path
from typing import Optional

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, RGBColor, Twips
from docx.text.paragraph import Paragraph

from app.skills_report import assets
from app.skills_report.content import ReportContent
from app.skills_report.types import ReportConfig, ReportExperience, SkillsReportData, SkillsReportOutputConfig
from app.skills_report.utils import (COLOR_DARK_BLUE, COLOR_GRAY_DARK, COLOR_GREY_700, COLOR_TEXT_BLACK,
                                     capitalize_first_letter, format_date, get_date_range_text, get_display_title,
                                     get_education_text, get_unique_skills, group_experiences_by_work_type,
                                     prettify_text)

_STYLES_TEMPLATE = Path(__file__).parent / "styles.xml"
_EMU_PER_PIXEL = 9525  # docx.js converts image sizes from pixels to EMU with this factor

# Number of skills that must always stay on the same page as "Top Skills" title
PINNED_SKILLS_COUNT = 2

_NBSP = " "


# ----------------------------------------------------------------------------------------------------------------------
# Low level helpers (docx.js-like Paragraph/TextRun options)
# ----------------------------------------------------------------------------------------------------------------------

def _set_paragraph(p: Paragraph, *, heading: Optional[str] = None, alignment: Optional[str] = None,
                   spacing_before: Optional[int] = None, spacing_after: Optional[int] = None,
                   keep_next: Optional[bool] = None, page_break_before: Optional[bool] = None,
                   borders: Optional[dict[str, dict]] = None):
    if heading:
        # docx.js HeadingLevel values are style ids (Title, Heading5, ...)
        p._p.get_or_add_pPr().style = heading
    fmt = p.paragraph_format
    if keep_next is not None:
        fmt.keep_with_next = keep_next
    if page_break_before is not None:
        fmt.page_break_before = page_break_before
    if borders:
        p_pr = p._p.get_or_add_pPr()
        p_bdr = OxmlElement("w:pBdr")
        for side in ("top", "left", "bottom", "right"):
            if side not in borders:
                continue
            options = borders[side]
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), options["style"])
            if "color" in options:
                el.set(qn("w:color"), options["color"].lstrip("#"))
            el.set(qn("w:sz"), str(options["size"]))
            if "space" in options:
                el.set(qn("w:space"), str(options["space"]))
            p_bdr.append(el)
        p_pr.insert_element_before(p_bdr, "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
                                   "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi",
                                   "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
                                   "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection",
                                   "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle",
                                   "w:rPr", "w:sectPr", "w:pPrChange")
    if spacing_before is not None:
        fmt.space_before = Twips(spacing_before)
    if spacing_after is not None:
        fmt.space_after = Twips(spacing_after)
    if alignment is not None:
        # set the raw value: python-docx's enum has no "start" (docx.js AlignmentType.START)
        p._p.get_or_add_pPr().get_or_add_jc().set(qn("w:val"), alignment)


def _add_text_run(p: Paragraph, text: str, *, bold: bool = False, italics: bool = False, size: Optional[int] = None,
                  color: Optional[str] = None, all_caps: bool = False, line_break: bool = False):
    """docx.js `new TextRun({...})`: the text is written verbatim (no tab/new line conversion)."""
    run = p.add_run()
    if bold:
        run.bold = True
    if italics:
        run.italic = True
    if all_caps:
        run.font.all_caps = True
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color.lstrip("#").upper())
    if size is not None:
        run.font.size = Pt(size / 2)
    if line_break:
        run.add_break()
    if text:  # docx.js only writes a <w:t> for a non empty text
        run._r.add_t(text)
    return run


def _add_image_run(p: Paragraph, url: str, width: float, height: float):
    """docx.js `new ImageRun({data, transformation: {width, height}})` (sizes in pixels)."""
    image = assets.try_load_image(url)
    if image is None:
        return None
    run = p.add_run()
    run.add_picture(io.BytesIO(image.data), width=Emu(round(width * _EMU_PER_PIXEL)),
                    height=Emu(round(height * _EMU_PER_PIXEL)))
    return run


def _clear_paragraph_style(p: Paragraph):
    """python-docx's default header/footer paragraph uses the Header/Footer style, docx.js paragraphs have none."""
    p_pr = p._p.pPr
    if p_pr is not None and p_pr.pStyle is not None:
        p_pr._remove_pStyle()


def _add_field_chars(run, instruction: str):
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, separate, end):
        run._r.append(el)


# ----------------------------------------------------------------------------------------------------------------------
# Document parts (mirror of the docx.js components)
# ----------------------------------------------------------------------------------------------------------------------

class _Builder:
    def __init__(self, data: SkillsReportData, config: SkillsReportOutputConfig, content: ReportContent):
        self.data = data
        self.config = config
        self.content = content
        self.doc: DocumentObject = Document()
        self._apply_styles()

    def _apply_styles(self):
        """Replace python-docx's default styles with docx.js's (docDefaults: Inter, black)."""
        styles_element = self.doc.styles.element
        for child in list(styles_element):
            styles_element.remove(child)
        template = parse_xml(_STYLES_TEMPLATE.read_bytes())
        for child in template:
            styles_element.append(child)

    def _p(self, container=None, **options) -> Paragraph:
        container = container or self.doc
        p = container.add_paragraph()
        _set_paragraph(p, **options)
        return p

    # --- constructSkillReportDocument.ts ---

    def _paragraph_with_image(self, text: str, image_url: str):
        p = self._p(alignment="left", spacing_after=50)
        _add_image_run(p, image_url, 18, 16)
        _add_text_run(p, _NBSP * 2)
        _add_text_run(p, text, color=COLOR_TEXT_BLACK, size=24)

    def _report_title(self):
        p = self._p(heading="Title", alignment="left", spacing_after=300)
        _add_text_run(p, self.content.skills_report_title, bold=True, color=COLOR_DARK_BLUE, size=32)

    def _personal_information(self):
        d = self.data
        if d.name:
            p = self._p(spacing_after=100)
            _add_text_run(p, d.name, color=COLOR_TEXT_BLACK, bold=True, size=28)
        if d.location:
            self._paragraph_with_image(d.location, assets.LOCATION_ICON)
        if d.email:
            self._paragraph_with_image(d.email, assets.EMAIL_ICON)
        if d.school or d.program:
            self._paragraph_with_image(get_education_text(d.program, d.school), assets.EDUCATION_ICON)

    def _report_description(self):
        p = self._p(alignment="start", spacing_before=300, spacing_after=200)
        text = prettify_text(self.content.report_body_text(format_date(self.data.conversation_conducted_at)))
        _add_text_run(p, text, size=22)

    def _section_divider(self):
        self._p(borders={"top": {"style": "single", "size": 10}}, spacing_before=200)

    # --- ConstructExperienceList.tsx ---

    def _experiences_section_header(self):
        p = self._p(heading="Heading5", alignment="left", spacing_before=100)
        _add_text_run(p, self.content.experiences_title, bold=True, size=28, color=COLOR_DARK_BLUE)

    def _work_type_section(self, experiences: list[ReportExperience], title: str, icon_url: str,
                           report_config: ReportConfig):
        if not experiences:
            return
        p = self._p(heading="Heading6", alignment="left", spacing_before=300, keep_next=True)
        _add_image_run(p, icon_url, 22, 22)
        _add_text_run(p, _NBSP * 2)
        _add_text_run(p, title, bold=True, size=26, color=COLOR_TEXT_BLACK)
        for experience in experiences:
            self._experience(experience, report_config)

    def _experience_list(self):
        c = self.content
        self._experiences_section_header()
        groups = group_experiences_by_work_type(self.data.experiences)
        report = self.config.report
        self._work_type_section(groups["salary_work"], c.salary_work_title, assets.EMPLOYEE_ICON, report)
        self._work_type_section(groups["unpaid_work"], c.unpaid_work_title, assets.COMMUNITY_WORK_ICON, report)
        self._work_type_section(groups["trainee_work"], c.trainee_work_title, assets.TRAINEE_WORK_ICON, report)
        self._work_type_section(groups["uncategorized"], c.uncategorized_title, assets.QUIZ_ICON, report)

    # --- experiencesReportContent/ExperiencesReportContent.tsx ---

    def _experience(self, experience: ReportExperience, report_config: ReportConfig):
        details = report_config.experience_details
        if details.title:
            p = self._p(spacing_after=100, spacing_before=300, keep_next=True)
            _add_text_run(p, get_display_title(experience), color=COLOR_TEXT_BLACK, bold=True, size=24)

        show_date_range = details.date_range and bool(experience.timeline.start or experience.timeline.end)
        show_company = details.company_name and bool(experience.company)
        show_location = details.location and bool(experience.location)
        if show_date_range or show_company or show_location:
            p = self._p(spacing_after=100)
            if show_date_range:
                _add_text_run(p, get_date_range_text(experience), color=COLOR_TEXT_BLACK, size=20)
            if show_date_range and show_company:
                _add_text_run(p, ", ")
            if show_company:
                _add_text_run(p, experience.company, color=COLOR_TEXT_BLACK, size=20)
            if show_location:
                _add_text_run(p, f" ({experience.location})", color=COLOR_TEXT_BLACK, size=20, italics=True)

        if details.summary and experience.summary:
            p = self._p(spacing_after=100)
            _add_text_run(p, experience.summary, color=COLOR_TEXT_BLACK, size=22)

        skills_count = len(experience.top_skills)
        p = self._p(spacing_after=100, keep_next=skills_count > 0)
        _add_text_run(p, self.content.top_skills_title, color=COLOR_TEXT_BLACK, bold=True, size=22)
        for index, skill in enumerate(experience.top_skills):
            p = self._p(spacing_after=100,
                        keep_next=index < PINNED_SKILLS_COUNT - 1 and index + 1 < skills_count)
            _add_text_run(p, f"• {capitalize_first_letter(skill.preferred_label)}", color=COLOR_TEXT_BLACK,
                          size=20)

    # --- ConstructSkillsDescription.tsx ---

    def _skills_description(self):
        skills = get_unique_skills(self.data.experiences)
        p = self._p(heading="Heading5", alignment="left", spacing_before=200, spacing_after=400,
                    page_break_before=True)
        _add_text_run(p, self.content.skills_description_title, bold=True, size=28, all_caps=True,
                      color=COLOR_DARK_BLUE)
        p = self._p()
        _add_text_run(p, self.content.skills_description_text, size=22)
        self._p(borders={"top": {"style": "single", "size": 10}}, spacing_before=200, spacing_after=100)
        for skill in skills:
            p = self._p(spacing_after=200)
            _add_text_run(p, capitalize_first_letter(skill.preferred_label), size=22, bold=True)
            _add_text_run(p, skill.description, size=20, line_break=True)

    # --- Header.tsx / Footer.tsx ---

    def _header(self, section):
        header = section.header
        header.is_linked_to_previous = False
        logos = self.config.logos
        p = header.paragraphs[0]
        _clear_paragraph_style(p)
        if not logos:
            # docx.js writes an empty header; python-docx keeps one (schema required) empty paragraph
            return
        _set_paragraph(p, alignment="left", spacing_after=300)
        for i, logo in enumerate(logos):
            _add_image_run(p, logo.url, logo.docx_styles.width, logo.docx_styles.height)
            if i < len(logos) - 1:
                _add_text_run(p, _NBSP * 5)

    def _footer(self, section):
        c = self.content
        footer = section.footer
        footer.is_linked_to_previous = False
        first = footer.paragraphs[0]
        _clear_paragraph_style(first)
        _set_paragraph(first, spacing_before=400)

        border = {"style": "single", "size": 2, "color": COLOR_GRAY_DARK}
        p = footer.add_paragraph()
        _set_paragraph(p, alignment="left", borders={
            "top": {**border, "space": 5},
            "bottom": {**border, "space": 10},
            "left": {**border, "space": 10},
            "right": {**border, "space": 5},
        })
        _add_image_run(p, assets.WARNING_ICON, 16, 14)
        _add_text_run(p, " ")
        _add_text_run(p, c.disclaimer_text_part1, size=18, color=COLOR_GREY_700)
        _add_text_run(p, c.disclaimer_text_part2, size=18, color=COLOR_TEXT_BLACK)
        _add_text_run(p, c.disclaimer_text_part3, size=18, color=COLOR_GREY_700)

        p = footer.add_paragraph()
        _set_paragraph(p, alignment="center", spacing_before=300)
        run = p.add_run()
        _add_field_chars(run, "PAGE")
        run._r.add_t("/")
        _add_field_chars(run, "NUMPAGES")

    def _section(self):
        section = self.doc.sections[0]
        section.page_width = Twips(11906)
        section.page_height = Twips(16838)
        section.top_margin = Twips(1440)
        section.bottom_margin = Twips(1440)
        section.left_margin = Twips(1000)
        section.right_margin = Twips(1000)
        section.header_distance = Twips(708)
        section.footer_distance = Twips(708)
        section.gutter = Twips(0)
        self._header(section)
        self._footer(section)

    def build(self) -> bytes:
        self._report_title()
        self._personal_information()
        if self.config.report.summary.show:
            self._report_description()
        self._section_divider()
        self._experience_list()
        self._skills_description()
        self._section()
        props = self.doc.core_properties
        props.title = self.content.skills_report_title
        props.author = self.content.app_name
        props.comments = ""
        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()


def generate_skills_report_docx(data: SkillsReportData, config: SkillsReportOutputConfig,
                                content: ReportContent) -> bytes:
    """Generate the skills report DOCX (same structure as the frontend docx.js report)."""
    return _Builder(data, config, content).build()

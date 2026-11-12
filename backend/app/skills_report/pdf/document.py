"""
The skills report PDF document tree.

This is a 1:1 mirror of the frontend react-pdf components (keep them in sync!):
  - frontend-new/src/experiences/report/reportPdf/SkillReportPDF.tsx
  - frontend-new/src/experiences/report/reportPdf/components/**
  - frontend-new/src/experiences/report/reportPdf/styles.ts

Text fragments mirror the JSX children (e.g. `({experience.location})` is three fragments "(", location, ")"),
because react-pdf shapes every fragment separately, which affects the glyph positions and therefore the line breaks.
"""
from typing import Optional

from app.skills_report import assets
from app.skills_report.content import ReportContent
from app.skills_report.pdf.layout import Image, ImageData, Node, Text, View
from app.skills_report.pdf.text_kit import Attributes, Fragment, load_font
from app.skills_report.types import ReportConfig, ReportExperience, SkillsReportData, SkillsReportOutputConfig
from app.skills_report.utils import (COLOR_DARK_BLUE, COLOR_GRAY_DARK, COLOR_SKILL_TEXT, COLOR_TEXT_BLACK,
                                     capitalize_first_letter, format_date, get_date_range_text, get_display_title,
                                     get_education_text, get_unique_skills, group_experiences_by_work_type,
                                     prettify_text)

# react-pdf "A4" page size
PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89

# Must match footer.height and logoContainer total height (styles.ts)
FOOTER_HEIGHT = 130
LOGO_HEIGHT = 96

# Number of skills that must always render together with the "Top Skills" title
PINNED_SKILLS_COUNT = 2

_DEFAULT_FONT_SIZE = 18  # react-pdf default when no fontSize is set


def _ph(value: float) -> dict:
    return {"paddingLeft": value, "paddingRight": value}


def _mh(value: float) -> dict:
    return {"marginLeft": value, "marginRight": value}


def _border(width: float) -> dict:
    return {"borderTopWidth": width, "borderRightWidth": width, "borderBottomWidth": width, "borderLeftWidth": width}


_BOLD = {"fontWeight": "bold"}
_ITALIC = {"fontStyle": "italic"}

# --- styles.ts (shorthands expanded) ---
STYLES: dict[str, dict] = {
    "page": {"flexDirection": "column", "paddingTop": LOGO_HEIGHT, "paddingBottom": FOOTER_HEIGHT,
             "color": COLOR_TEXT_BLACK, "width": PAGE_WIDTH, "height": PAGE_HEIGHT},
    "title": {"fontSize": 16, "paddingBottom": 18, "color": COLOR_DARK_BLUE, **_ph(48), **_BOLD},
    "subtitle": {"fontSize": 14, **_BOLD},
    "text": {"fontSize": 12},
    "experiencesTitle": {"fontSize": 14, **_ph(48), "color": COLOR_DARK_BLUE, **_BOLD},
    "body": {"flexDirection": "column"},
    "rowView": {"flexDirection": "row", "alignItems": "center", "gap": 6},
    "column": {"flexDirection": "column", "gap": 4, **_ph(48)},
    "bodyText": {"fontSize": 11, **_ph(48)},
    "experiencesContainer": {"flexDirection": "column", **_ph(48), "paddingTop": 16},
    "categoryContainer": {"flexDirection": "column", "paddingBottom": 10},
    "categoryTitleContainer": {"flexDirection": "row", "alignItems": "center", "paddingBottom": 12},
    "categoryIcon": {"height": 13, "paddingBottom": 2, "marginRight": 8},
    "categoryTitle": {"fontSize": 13, **_BOLD},
    "container": {"flexDirection": "column", "paddingBottom": 14},
    "experienceTitle": {"fontSize": 12, **_BOLD},
    "summary": {"fontSize": 11, "paddingBottom": 6},
    "experienceInfo": {"flexDirection": "row", "alignItems": "center", "fontSize": 10, "paddingTop": 6,
                       "paddingBottom": 6},
    "location": {"paddingLeft": 4, **_ITALIC},
    # `borderBottomWidth: 1, border: 1` -> all borders 1
    "divider": {**_mh(48), **_border(1), "marginTop": 12, "marginBottom": 16},
    "logoContainer": {"flexDirection": "row", "alignItems": "center", "paddingBottom": 18, **_ph(48),
                      "paddingTop": 32, "gap": 26, "position": "absolute", "top": 0, "width": "100%"},
    "infoIcons": {"width": 14, "height": 12},
    # maxWidth/maxHeight: 100% of the 14x12 infoIcons box
    "infoIcon": {"maxWidth": 14, "maxHeight": 12, "objectFit": "contain"},
    "skillsTitle": {"fontSize": 11, "paddingBottom": 4, **_BOLD},
    "skillText": {"fontSize": 10, "color": COLOR_SKILL_TEXT},
    "skillsContainer": {"flexDirection": "column", "alignItems": "flex-start"},
    "skillItem": {"paddingBottom": 4},
    "skillDescriptionContainer": {"flexDirection": "column", **_ph(48)},
    "skillDescriptionTitle": {"fontSize": 16, "paddingBottom": 18, "color": COLOR_DARK_BLUE, **_BOLD},
    "info": {"fontSize": 11},
    "skillDivider": {**_border(1), "marginTop": 12, "marginBottom": 20},
    "skillContainer": {"flexDirection": "column", "gap": 4},
    "label": {"fontSize": 11, **_BOLD},
    "description": {"fontSize": 10, "paddingBottom": 12},
    "footer": {"width": "100%", "height": FOOTER_HEIGHT, "flexDirection": "column", "paddingTop": 20,
               "paddingBottom": 26, "position": "absolute", "gap": 16, "bottom": 0},
    "disclaimerContainer": {"flexDirection": "row", **_mh(48), "paddingTop": 8, "paddingRight": 8,
                            "paddingBottom": 8, "paddingLeft": 8, **_border(1)},
    "disclaimerText": {"flex": 1, "fontSize": 9, "color": COLOR_GRAY_DARK},
    "disclaimerTextBold": {"fontSize": 9, "color": COLOR_TEXT_BLACK},
    "disclaimerIcon": {"width": 12, "height": 12},
    "pageNumber": {"fontSize": 10, "textAlign": "center"},
}

_TEXT_PROPERTIES = {"color", "fontSize", "fontWeight", "fontStyle", "textAlign", "lineHeight"}
_INHERITABLE = _TEXT_PROPERTIES


def _font_for(style: dict):
    if style.get("fontWeight") == "bold":
        return load_font(assets.INTER.bold, "Inter-Bold")
    if style.get("fontStyle") == "italic":
        return load_font(assets.INTER.italic, "Inter-Italic")
    return load_font(assets.INTER.regular, "Inter-Regular")


def _attributes(style: dict) -> Attributes:
    font_size = style.get("fontSize") or _DEFAULT_FONT_SIZE
    line_height = style.get("lineHeight")
    return Attributes(font=_font_for(style), font_size=font_size, color=style.get("color") or "black",
                      align=style.get("textAlign") or "left",
                      line_height=line_height * font_size if line_height else None)


class _Builder:
    def __init__(self, data: SkillsReportData, config: SkillsReportOutputConfig, content: ReportContent):
        self.data = data
        self.config = config
        self.content = content

    # --- helpers ---------------------------------------------------------------------------------------------------

    @staticmethod
    def _inherit(inherited: dict, style: dict) -> dict:
        return {**inherited, **{k: v for k, v in style.items() if k in _INHERITABLE}}

    def _text(self, inherited: dict, style: dict, *children, **props) -> Node:
        """A <Text> with string and nested-<Text> children: children are str or (style, [str, ...])"""
        text_style = self._inherit(inherited, style)
        fragments: list[Fragment] = []
        for child in children:
            if child is None or child is False:
                continue
            if isinstance(child, tuple):
                nested_style, nested_children = child
                nested_text_style = self._inherit(text_style, nested_style)
                fragments.extend(Fragment(str(c), _attributes(nested_text_style)) for c in nested_children
                                 if c is not None)
            else:
                fragments.append(Fragment(str(child), _attributes(text_style)))
        return Text(style=style, fragments=fragments, **props)

    @staticmethod
    def _image(url: str, style: dict) -> Optional[Node]:
        image = assets.try_load_image(url)
        if image is None:
            return None
        return Image(ImageData(image.data, image.width, image.height), style=style)

    # --- components ------------------------------------------------------------------------------------------------

    def _experience(self, inherited: dict, experience: ReportExperience, report_config: ReportConfig) -> Node:
        details = report_config.experience_details
        start, end = experience.timeline.start, experience.timeline.end
        show_date_range = details.date_range and bool(start or end)
        date_range_text = get_date_range_text(experience)
        show_company = details.company_name and bool(experience.company)
        show_location = details.location and bool(experience.location)
        show_summary = details.summary and bool(experience.summary)
        show_title = details.title
        display_title = get_display_title(experience)
        pinned_skills = experience.top_skills[:PINNED_SKILLS_COUNT]
        remaining_skills = experience.top_skills[PINNED_SKILLS_COUNT:]
        s = STYLES

        container_inherited = self._inherit(inherited, s["container"])
        header_children: list[Optional[Node]] = []
        if show_title:
            header_children.append(self._text(container_inherited, s["experienceTitle"], display_title))
        if show_date_range or show_company or show_location:
            info_inherited = self._inherit(container_inherited, s["experienceInfo"])
            header_children.append(View(s["experienceInfo"], [
                self._text(info_inherited, {}, date_range_text) if show_date_range else None,
                self._text(info_inherited, {}, ",", " ") if show_date_range and show_company else None,
                self._text(info_inherited, {}, experience.company) if show_company else None,
                self._text(info_inherited, s["location"], "(", experience.location, ")") if show_location else None,
            ]))

        skill_style = {**s["skillText"], **s["skillItem"]}
        skills_inherited = self._inherit(container_inherited, s["skillsContainer"])
        return View(s["container"], [
            View({}, header_children, wrap=False, minPresenceAhead=50),
            View({}, [self._text(container_inherited, s["summary"], experience.summary)]) if show_summary else None,
            View(s["skillsContainer"], [
                View({}, [
                    self._text(skills_inherited, s["skillsTitle"], self.content.top_skills_title),
                    *[self._text(skills_inherited, skill_style, "• ", capitalize_first_letter(skill.preferred_label))
                      for skill in pinned_skills],
                ], wrap=False),
                *[View({}, [self._text(skills_inherited, skill_style, "• ",
                                       capitalize_first_letter(skill.preferred_label))], wrap=False)
                  for skill in remaining_skills],
            ]),
        ])

    def _experience_category(self, inherited: dict, title: str, icon: str,
                             experiences: list[ReportExperience]) -> Optional[Node]:
        if not experiences:
            return None
        s = STYLES
        category_inherited = self._inherit(inherited, s["categoryContainer"])
        return View(s["categoryContainer"], [
            View(s["categoryTitleContainer"], [
                self._image(icon, s["categoryIcon"]),
                self._text(category_inherited, s["categoryTitle"], title),
            ], wrap=False, minPresenceAhead=60),
            *[self._experience(category_inherited, e, self.config.report) for e in experiences],
        ])

    def _personal_info(self, inherited: dict, value: Optional[str], icon: str) -> Optional[Node]:
        if not value:
            return None
        s = STYLES
        return View(s["rowView"], [
            View(s["infoIcons"], [self._image(icon, s["infoIcon"])]),
            self._text(inherited, s["text"], value),
        ])

    def _skills_description(self, inherited: dict) -> Node:
        s = STYLES
        skills = get_unique_skills(self.data.experiences)
        container_inherited = self._inherit(inherited, s["skillDescriptionContainer"])
        return View(s["skillDescriptionContainer"], [
            self._text(container_inherited, s["skillDescriptionTitle"], self.content.skills_description_title),
            View({}, [self._text(container_inherited, s["info"], self.content.skills_description_text)]),
            View(s["skillDivider"]),
            *[View(s["skillContainer"], [
                self._text(container_inherited, s["label"], capitalize_first_letter(skill.preferred_label)),
                self._text(container_inherited, s["description"], skill.description),
            ], wrap=False) for skill in skills],
        ], **{"break": True})

    def _footer(self, inherited: dict) -> Node:
        s = STYLES
        c = self.content
        footer_inherited = self._inherit(inherited, s["footer"])
        page_number_style = self._inherit(footer_inherited, s["pageNumber"])

        def render_page_number(page_number: int, total_pages: Optional[int]) -> list[Fragment]:
            total = "undefined" if total_pages is None else str(total_pages)
            return [Fragment(f"{page_number} / {total}", _attributes(page_number_style))]

        return View(s["footer"], [
            View(s["disclaimerContainer"], [
                self._image(assets.WARNING_ICON, s["disclaimerIcon"]),
                self._text(footer_inherited, s["disclaimerText"], " ", c.disclaimer_text_part1, " ",
                           (s["disclaimerTextBold"], [c.disclaimer_text_part2, " "]), c.disclaimer_text_part3),
            ]),
            Text(style=s["pageNumber"], render=render_page_number),
        ], fixed=True)

    # --- document ----------------------------------------------------------------------------------------------------

    def build(self) -> Node:
        d = self.data
        s = STYLES
        c = self.content
        page_inherited = self._inherit({}, s["page"])
        groups = group_experiences_by_work_type(d.experiences)
        has_personal_info = bool(d.name or d.location or d.email or d.school or d.program)
        column_inherited = self._inherit(page_inherited, s["column"])

        personal_info = View({**s["column"], "paddingBottom": 18 if has_personal_info else 0}, [
            self._text(column_inherited, s["subtitle"], d.name) if d.name else None,
            self._personal_info(column_inherited, d.location, assets.LOCATION_ICON),
            self._personal_info(column_inherited, d.email, assets.EMAIL_ICON),
            View(s["rowView"], [
                View(s["infoIcons"], [self._image(assets.EDUCATION_ICON, s["infoIcon"])]),
                self._text(column_inherited, s["text"], get_education_text(d.program, d.school)),
            ]) if d.school or d.program else None,
        ])

        experiences_inherited = self._inherit(page_inherited, s["experiencesContainer"])
        body = View(s["body"], [
            self._text(page_inherited, s["title"], c.skills_report_title),
            personal_info,
            View({}, [self._text(page_inherited, s["bodyText"],
                                 prettify_text(c.report_body_text(format_date(d.conversation_conducted_at))))])
            if self.config.report.summary.show else None,
            View(s["divider"]),
            self._text(page_inherited, s["experiencesTitle"], c.experiences_title),
            View(s["experiencesContainer"], [
                self._experience_category(experiences_inherited, c.salary_work_title, assets.EMPLOYEE_ICON,
                                          groups["salary_work"]),
                self._experience_category(experiences_inherited, c.unpaid_work_title, assets.COMMUNITY_WORK_ICON,
                                          groups["unpaid_work"]),
                self._experience_category(experiences_inherited, c.trainee_work_title, assets.TRAINEE_WORK_ICON,
                                          groups["trainee_work"]),
                self._experience_category(experiences_inherited, c.uncategorized_title, assets.QUIZ_ICON,
                                          groups["uncategorized"]),
            ]),
            self._skills_description(page_inherited),
        ])

        logos = View(s["logoContainer"], [self._image(logo.url, dict(logo.pdf_styles)) for logo in self.config.logos],
                     fixed=True)
        return Node("page", style=dict(s["page"]), children=[logos, body, self._footer(page_inherited)])


def build_document(data: SkillsReportData, config: SkillsReportOutputConfig, content: ReportContent) -> Node:
    return _Builder(data, config, content).build()

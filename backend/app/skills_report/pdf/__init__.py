from app.skills_report.content import ReportContent
from app.skills_report.pdf.document import FOOTER_HEIGHT, LOGO_HEIGHT, PAGE_HEIGHT, build_document
from app.skills_report.pdf.layout import LayoutContext, layout_page, paginate
from app.skills_report.pdf.render import render_pdf
from app.skills_report.types import SkillsReportData, SkillsReportOutputConfig


def generate_skills_report_pdf(data: SkillsReportData, config: SkillsReportOutputConfig,
                               content: ReportContent) -> bytes:
    """Generate the skills report PDF (same layout as the frontend react-pdf report)."""
    ctx = LayoutContext(page_height=PAGE_HEIGHT, page_padding_top=LOGO_HEIGHT, page_padding_bottom=FOOTER_HEIGHT)
    page = layout_page(build_document(data, config, content), ctx)
    pages = paginate(page, ctx)
    return render_pdf(pages, title=content.skills_report_title, author=content.app_name)

"""
Skills report (CV) generation in the backend.

The frontend generates the same report in the browser (react-pdf for PDF, docx.js for DOCX); this package reproduces
both formats server side. `scripts/skills_report_parity/run_parity.py` checks that both implementations generate the
same documents for the same input.
"""
from app.skills_report.service import generate_skills_report_docx, generate_skills_report_pdf

__all__ = ["generate_skills_report_pdf", "generate_skills_report_docx"]

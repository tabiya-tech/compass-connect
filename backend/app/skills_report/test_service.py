"""
Tests of the skills report generation.

The parity with the frontend is checked against the "golden" canonical hashes of the frontend documents
(scripts/skills_report_parity/golden, written by `run_parity.py --write-golden`), so these tests run without node.
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from docx import Document

from app.i18n.types import Locale
from app.skills_report import generate_skills_report_docx, generate_skills_report_pdf
from app.skills_report.content import ReportContent
from app.skills_report.types import SkillsReportData, merge_skills_report_config

PARITY_DIR = Path(__file__).resolve().parents[2] / "scripts" / "skills_report_parity"
FIXTURES = sorted((PARITY_DIR / "fixtures").glob("*.json"))


def _generate(fixture_path: Path, fmt: str) -> bytes:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    generate = generate_skills_report_pdf if fmt == "pdf" else generate_skills_report_docx
    return generate(SkillsReportData.model_validate(fixture["props"]), locale=Locale(fixture["locale"]),
                    app_name=fixture["appName"], config=merge_skills_report_config(fixture["config"]))


@pytest.fixture(name="canonical", scope="module")
def _canonical():
    sys.path.insert(0, str(PARITY_DIR))
    import canonical_docx  # pylint: disable=import-outside-toplevel,import-error
    import canonical_pdf  # pylint: disable=import-outside-toplevel,import-error
    return {"pdf": canonical_pdf.canonicalize_pdf, "docx": canonical_docx.canonicalize_docx}


class TestParityWithFrontend:
    @pytest.mark.parametrize("fixture_path", FIXTURES, ids=[f.stem for f in FIXTURES])
    @pytest.mark.parametrize("fmt", ["pdf", "docx"])
    def test_backend_document_matches_the_frontend_document(self, fixture_path, fmt, canonical, tmp_path):
        # GIVEN a parity fixture and the canonical hash of the document the frontend generates for it
        golden = json.loads((PARITY_DIR / "golden" / fixture_path.name).read_text(encoding="utf-8"))[fmt]
        # WHEN the backend generates the document
        output = tmp_path / f"report.{fmt}"
        output.write_bytes(_generate(fixture_path, fmt))
        # THEN the canonical hash of the backend document is the hash of the frontend document
        actual = canonical[fmt](output)
        assert actual.content_hash == golden["canonical_sha256"], \
            f"Run scripts/skills_report_parity/run_parity.py -f {fixture_path.stem} to see the differences"


class TestGenerateSkillsReportPdf:
    def test_generates_a_deterministic_pdf(self):
        # GIVEN a report
        given_fixture = FIXTURES[0]
        # WHEN the PDF is generated twice
        first = _generate(given_fixture, "pdf")
        second = _generate(given_fixture, "pdf")
        # THEN it is a PDF
        assert first.startswith(b"%PDF-")
        # AND the same input always gives the same bytes
        assert first == second

    def test_generates_a_pdf_for_an_empty_report(self):
        # GIVEN a report without any data
        # WHEN the PDF is generated
        actual = generate_skills_report_pdf(SkillsReportData(), locale=Locale.EN_US, app_name="Compass")
        # THEN a PDF is generated
        assert actual.startswith(b"%PDF-")


class TestGenerateSkillsReportDocx:
    def test_generates_a_docx_that_word_processors_can_open(self):
        # GIVEN a report
        given_fixture = FIXTURES[0]
        # WHEN the DOCX is generated
        actual = _generate(given_fixture, "docx")
        # THEN it is a valid DOCX package that python-docx can read
        with zipfile.ZipFile(io.BytesIO(actual)) as zf:
            assert "word/document.xml" in zf.namelist()
        document = Document(io.BytesIO(actual))
        # AND it starts with the report title
        assert document.paragraphs[0].text == "Skills Report"

    def test_generates_a_docx_for_an_empty_report_without_logos(self):
        # GIVEN a report without any data and without logos
        # WHEN the DOCX is generated
        actual = generate_skills_report_docx(SkillsReportData(), locale=Locale.EN_US, app_name="Compass",
                                             config=merge_skills_report_config({"logos": []}))
        # THEN a readable DOCX is generated
        assert Document(io.BytesIO(actual)).paragraphs[0].text == "Skills Report"


class TestReportContent:
    @pytest.mark.parametrize("locale", list(Locale), ids=[locale.value for locale in Locale])
    def test_every_locale_has_the_report_texts(self, locale):
        # GIVEN the report content for a locale
        given_content = ReportContent(locale=locale, app_name="MyApp")
        # WHEN the texts are resolved
        texts = [given_content.skills_report_title, given_content.experiences_title,
                 given_content.top_skills_title, given_content.skills_description_text,
                 given_content.disclaimer_text_part3, given_content.report_body_text("March 14, 2025")]
        # THEN no text is missing
        assert all(texts)
        # AND the app name and the date are interpolated
        assert "MyApp" in given_content.skills_description_text
        assert "March 14, 2025" in given_content.report_body_text("March 14, 2025")
        assert "{" not in "".join(texts)

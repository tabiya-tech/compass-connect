#!/usr/bin/env python3
"""
Skills report parity check: frontend (react-pdf / docx.js) vs backend (reportlab / python-docx).

For every fixture in `fixtures/` this script
  1. generates the PDF and DOCX with the real frontend code (a Jest runner in frontend-new, see
     frontend-new/src/experiences/report/_parity/generateParityReports.test.tsx),
  2. generates the PDF and DOCX with the backend (app.skills_report),
  3. reduces every file to a canonical model (see canonical_pdf.py / canonical_docx.py) and compares the SHA-256 of
     the canonical models. The raw file bytes of two different engines can never be identical, the canonical model
     captures what a reader sees: pages, text lines and their styles, images, paragraphs, runs, fields, etc.
  4. for PDFs, additionally compares the position of every line, image and border, with a tolerance (default 0.5pt).

Usage (from the backend directory, with the backend venv activated and the frontend dependencies installed):

    python scripts/skills_report_parity/run_parity.py                 # all fixtures
    python scripts/skills_report_parity/run_parity.py -f 04_multipage_two_logos_long_content
    python scripts/skills_report_parity/run_parity.py --skip-frontend --out-dir /tmp/parity   # reuse frontend files
    python scripts/skills_report_parity/run_parity.py --write-golden  # store the frontend canonical hashes, used by
                                                                      # the backend unit tests (no node needed there)

Exit code 0 when every fixture matches, 1 otherwise. Diffs of the canonical models of mismatching files are written
to <out-dir>/<fixture>/*.diff.
"""
import argparse
import difflib
import hashlib
import json
import os
# runs the frontend test runner with fixed arguments
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent.parent
REPO_DIR = BACKEND_DIR.parent
FRONTEND_DIR = REPO_DIR / "frontend-new"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
GOLDEN_DIR = SCRIPT_DIR / "golden"
FRONTEND_GENERATOR = "src/experiences/report/_parity"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from canonical_docx import canonicalize_docx  # noqa: E402
from canonical_pdf import canonicalize_pdf, compare_layout  # noqa: E402
from app.i18n.types import Locale  # noqa: E402
from app.skills_report.assets import IMAGES_DIR, rasterize_svg  # noqa: E402
from app.skills_report.service import generate_skills_report_docx, generate_skills_report_pdf  # noqa: E402
from app.skills_report.types import SkillsReportData, merge_skills_report_config  # noqa: E402


def _load_fixtures(fixtures_dir: Path, names: list[str]) -> dict[str, dict]:
    fixtures = {}
    for path in sorted(fixtures_dir.glob("*.json")):
        if names and path.stem not in names:
            continue
        fixtures[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    missing = set(names) - set(fixtures)
    if missing:
        raise SystemExit(f"Unknown fixture(s): {', '.join(sorted(missing))}")
    return fixtures


def _prepare_raster_dir(out_dir: Path) -> Path:
    """
    The browser rasterizes SVG logos on a canvas before embedding them; that is not available in Jest. Give the
    frontend generator the backend's PNG rendering so both sides embed the exact same bitmap.
    """
    raster_dir = out_dir / "_raster"
    raster_dir.mkdir(parents=True, exist_ok=True)
    for svg in IMAGES_DIR.glob("*.svg"):
        (raster_dir / (svg.stem + ".png")).write_bytes(rasterize_svg(svg.read_bytes()))
    return raster_dir


def _generate_frontend(fixtures: dict[str, dict], out_dir: Path, raster_dir: Path):
    fixtures_dir = out_dir / "_fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    for old in fixtures_dir.glob("*.json"):
        old.unlink()
    for name, fixture in fixtures.items():
        (fixtures_dir / f"{name}.json").write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    env = {
        **os.environ,
        "CI": "true",
        "REPORT_PARITY_FIXTURES_DIR": str(fixtures_dir),
        "REPORT_PARITY_OUT_DIR": str(out_dir),
        "REPORT_PARITY_RASTER_DIR": str(raster_dir),
    }
    cmd = ["npx", "react-scripts", "test", "--watchAll=false", "--coverage=false", FRONTEND_GENERATOR]
    print(f"Generating the frontend reports ({' '.join(cmd)}) ...", flush=True)
    result = subprocess.run(cmd, cwd=FRONTEND_DIR, env=env, capture_output=True, text=True,  # nosec B603
                            check=False)
    if result.returncode != 0:
        print(result.stdout[-5000:])
        print(result.stderr[-5000:])
        raise SystemExit("The frontend generator failed (see the output above)")


def _generate_backend(name: str, fixture: dict, out_dir: Path):
    data = SkillsReportData.model_validate(fixture["props"])
    config = merge_skills_report_config(fixture.get("config"))
    locale = Locale(fixture["locale"])
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "backend.pdf").write_bytes(
        generate_skills_report_pdf(data, locale=locale, app_name=fixture["appName"], config=config))
    (target / "backend.docx").write_bytes(
        generate_skills_report_docx(data, locale=locale, app_name=fixture["appName"], config=config))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_diff(path: Path, frontend: dict, backend: dict):
    a = json.dumps(frontend, indent=1, ensure_ascii=False, sort_keys=True).splitlines()
    b = json.dumps(backend, indent=1, ensure_ascii=False, sort_keys=True).splitlines()
    path.write_text("\n".join(difflib.unified_diff(a, b, "frontend", "backend", lineterm="")), encoding="utf-8")


def _compare(name: str, out_dir: Path, layout_tolerance: float) -> dict:
    target = out_dir / name
    result = {"fixture": name}

    front_pdf, back_pdf = canonicalize_pdf(target / "frontend.pdf"), canonicalize_pdf(target / "backend.pdf")
    layout = compare_layout(front_pdf, back_pdf)
    max_deviation = max(layout["lines"], layout["images"], layout["graphics"])
    result["pdf"] = {
        "frontend_hash": front_pdf.content_hash,
        "backend_hash": back_pdf.content_hash,
        "match": front_pdf.content_hash == back_pdf.content_hash,
        "pages": front_pdf.content["page_count"],
        "layout_max_deviation_pt": max_deviation,
        "layout_ok": max_deviation <= layout_tolerance and not layout["graphics_count_mismatch"],
        "layout": layout,
        "raw_sha256": {"frontend": _sha256(target / "frontend.pdf"), "backend": _sha256(target / "backend.pdf")},
    }
    if not result["pdf"]["match"]:
        _write_diff(target / "pdf.diff", front_pdf.content, back_pdf.content)

    front_docx, back_docx = canonicalize_docx(target / "frontend.docx"), canonicalize_docx(target / "backend.docx")
    result["docx"] = {
        "frontend_hash": front_docx.content_hash,
        "backend_hash": back_docx.content_hash,
        "match": front_docx.content_hash == back_docx.content_hash,
        "raw_sha256": {"frontend": _sha256(target / "frontend.docx"), "backend": _sha256(target / "backend.docx")},
    }
    if not result["docx"]["match"]:
        _write_diff(target / "docx.diff", front_docx.content, back_docx.content)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-f", "--fixture", action="append", default=[], help="Run only this fixture (repeatable)")
    parser.add_argument("--fixtures-dir", type=Path, default=FIXTURES_DIR,
                        help=f"Directory with the fixtures (default: {FIXTURES_DIR.relative_to(BACKEND_DIR)})")
    parser.add_argument("--out-dir", type=Path, help="Where to write the generated files (default: a temp dir)")
    parser.add_argument("--skip-frontend", action="store_true",
                        help="Do not run the frontend generator, reuse the frontend files in --out-dir")
    parser.add_argument("--layout-tolerance", type=float, default=0.5,
                        help="Maximum PDF positional deviation in points (default: 0.5)")
    parser.add_argument("--write-golden", action="store_true",
                        help="Write the frontend canonical hashes to golden/<fixture>.json")
    args = parser.parse_args()

    fixtures = _load_fixtures(args.fixtures_dir, args.fixture)
    out_dir = (args.out_dir or Path(tempfile.mkdtemp(prefix="skills-report-parity-"))).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")

    if not args.skip_frontend:
        _generate_frontend(fixtures, out_dir, _prepare_raster_dir(out_dir))
    for name, fixture in fixtures.items():
        _generate_backend(name, fixture, out_dir)

    results = [_compare(name, out_dir, args.layout_tolerance) for name in fixtures]
    (out_dir / "parity-report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    if args.write_golden:
        GOLDEN_DIR.mkdir(exist_ok=True)
        for r in results:
            (GOLDEN_DIR / f"{r['fixture']}.json").write_text(json.dumps({
                "pdf": {"canonical_sha256": r["pdf"]["frontend_hash"], "pages": r["pdf"]["pages"]},
                "docx": {"canonical_sha256": r["docx"]["frontend_hash"]},
            }, indent=2) + "\n", encoding="utf-8")
        print(f"Golden hashes written to {GOLDEN_DIR}")

    ok = True
    width = max(len(n) for n in fixtures) + 2
    print()
    print(f"{'fixture':<{width}} {'format':<6} {'frontend (canonical sha256)':<18} {'backend (canonical sha256)':<18} "
          f"result")
    for r in results:
        for fmt in ("pdf", "docx"):
            fr = r[fmt]
            status = "MATCH" if fr["match"] else "MISMATCH"
            if fmt == "pdf":
                layout_status = "layout ok" if fr["layout_ok"] else "LAYOUT DEVIATION"
                status += f" ({fr['pages']} pages, max deviation {fr['layout_max_deviation_pt']}pt, {layout_status})"
                ok = ok and fr["layout_ok"]
            ok = ok and fr["match"]
            print(f"{r['fixture']:<{width}} {fmt:<6} {fr['frontend_hash'][:16]:<18} {fr['backend_hash'][:16]:<18} "
                  f"{status}")
    print()
    print("ALL MATCH" if ok else f"PARITY FAILURES, see the *.diff files and {out_dir / 'parity-report.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

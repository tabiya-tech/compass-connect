/**
 * Frontend <-> backend skills report parity generator.
 *
 * This is NOT a regular unit test. It renders the shared parity fixtures with the real frontend
 * PDF (@react-pdf/renderer) and DOCX (docx) code and writes the files to disk, so that
 * `backend/scripts/skills_report_parity/run_parity.py` can compare them with the files the backend
 * generates from the same fixtures.
 *
 * It is skipped unless the following environment variables are set (run_parity.py sets them):
 *   - REPORT_PARITY_FIXTURES_DIR: directory with the *.json fixtures
 *   - REPORT_PARITY_OUT_DIR: directory to write <fixture>/frontend.pdf and <fixture>/frontend.docx into
 *   - REPORT_PARITY_RASTER_DIR: directory with PNG renderings of the SVG images (<basename>.png), so both
 *     sides embed the exact same logo bitmap (the browser rasterizes SVGs on a canvas, which is not available here)
 */
import fs from "fs";
import path from "path";

const FIXTURES_DIR = process.env.REPORT_PARITY_FIXTURES_DIR;
const OUT_DIR = process.env.REPORT_PARITY_OUT_DIR;
const mockRasterDir = process.env.REPORT_PARITY_RASTER_DIR;
const mockPublicDir = path.resolve(__dirname, "../../../../public");

// The tests run in jsdom, where Node's Buffers (from zlib, fs, TextEncoder) come from another realm and are not
// `instanceof Uint8Array`. pdfkit (`PDFReference._write`) then stringifies every binary stream chunk as UTF-8,
// which corrupts the embedded fonts and images (the PDF text layer is intact, but every glyph renders as a dot
// and the images are blank). Make `instanceof Uint8Array` realm-independent, as it is in a browser.
Object.defineProperty(Uint8Array, Symbol.hasInstance, {
  value: (value: unknown) =>
    ArrayBuffer.isView(value) && Object.prototype.toString.call(value) === "[object Uint8Array]",
});

// The product name is read at render time, so it can be switched per fixture.
// (Kept on globalThis because the imports below are hoisted above any module-level `let`.)
const setAppName = (appName: string) => ((globalThis as any).__REPORT_PARITY_APP_NAME__ = appName);

jest.mock("src/envService", () => {
  const actual = jest.requireActual("src/envService");
  return {
    ...actual,
    getProductName: () => (globalThis as any).__REPORT_PARITY_APP_NAME__ ?? "Compass",
    getSupportedLocales: () => JSON.stringify(["en-GB", "en-US", "es-ES", "es-AR", "sw-KE", "ny-ZM", "pt-MZ"]),
    getDefaultLocale: () => "en-GB",
    getLocaleTextOverrides: () => ({}),
  };
});

// The global test setup mocks i18n with a fixed English `t`; the parity run needs the real, locale-aware i18n.
jest.unmock("src/i18n/i18n");
jest.unmock("react-i18next");

jest.mock("src/auth/firebaseConfig", () => ({
  updateLanguage: jest.fn(),
}));

jest.mock("src/experiences/report/util", () => {
  const actual = jest.requireActual("src/experiences/report/util");
  const nodeFs = jest.requireActual("fs");
  const nodePath = jest.requireActual("path");
  return {
    ...actual,
    getBase64Image: async (url: string) => {
      const basename = nodePath.basename(url);
      let filePath = nodePath.join(mockPublicDir, basename);
      if (basename.toLowerCase().endsWith(".svg")) {
        if (!mockRasterDir) throw new Error("REPORT_PARITY_RASTER_DIR is required to render SVG images");
        filePath = nodePath.join(mockRasterDir, basename.replace(/\.svg$/i, ".png"));
      }
      const data = nodeFs.readFileSync(filePath);
      return `data:image/png;base64,${data.toString("base64")}`;
    },
  };
});

import type { ReactElement } from "react";

type ParityFixture = {
  description: string;
  locale: string;
  appName: string;
  config: any;
  props: {
    name: string;
    email: string;
    location: string;
    school: string;
    program: string;
    conversationConductedAt: string | null;
    experiences: any[];
  };
};

const loadFixtures = (): [string, ParityFixture][] => {
  if (!FIXTURES_DIR) return [];
  return fs
    .readdirSync(FIXTURES_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => [f.replace(/\.json$/, ""), JSON.parse(fs.readFileSync(path.join(FIXTURES_DIR, f), "utf-8"))]);
};

const describeIfEnabled = FIXTURES_DIR && OUT_DIR ? describe : describe.skip;

/**
 * Fresh instances of the report modules (and of react-pdf/fontkit/docx) for every fixture.
 *
 * fontkit caches glyph objects (with the code points they were first created with) for the lifetime of the font,
 * and react-pdf keeps the fonts registered for the lifetime of the page. Rendering several reports in the same
 * process therefore makes the output of a report depend on the reports rendered before it (e.g. some glyphs end up
 * without a ToUnicode mapping). Each fixture is rendered as if it was the first report of a fresh page load.
 */
const loadReportModules = () => {
  let modules: any;
  jest.isolateModules(() => {
    const renderer = require("@react-pdf/renderer");
    // The app registers the fonts with URLs served by the dev server; in node they must be file paths.
    require("src/experiences/report/reportPdf/styles");
    renderer.Font.clear();
    const fontDir = path.join(mockPublicDir, "fonts/Inter-4.0/ttf");
    renderer.Font.register({
      family: "Inter",
      fonts: [
        { src: path.join(fontDir, "Inter-Regular.ttf"), fontWeight: "normal" },
        { src: path.join(fontDir, "Inter-Bold.ttf"), fontWeight: "bold" },
        { src: path.join(fontDir, "Inter-Italic.ttf"), fontStyle: "italic" },
      ],
    });
    modules = {
      React: require("react"),
      renderToBuffer: renderer.renderToBuffer,
      Packer: require("docx").Packer,
      i18n: require("src/i18n/i18n").default,
      SkillReportPDF: require("src/experiences/report/reportPdf/SkillReportPDF").default,
      constructSkillReportDocument: require("src/experiences/report/reportDocx/constructSkillReportDocument")
        .constructSkillReportDocument,
      mergeSkillsReportConfig: require("src/experiences/report/config/getConfig").mergeSkillsReportConfig,
    };
  });
  return modules;
};

describeIfEnabled("skills report parity: generate frontend reports", () => {
  const fixtures = loadFixtures();

  test.each(fixtures.length ? fixtures : [["<none>", null as unknown as ParityFixture]])(
    "%s",
    async (fixtureName, fixture) => {
      if (!fixture) throw new Error(`No fixtures found in ${FIXTURES_DIR}`);
      const m = loadReportModules();
      setAppName(fixture.appName);
      await m.i18n.changeLanguage(fixture.locale);
      expect(m.i18n.language).toBe(fixture.locale);

      const config = m.mergeSkillsReportConfig(fixture.config);
      const props = { ...fixture.props, config };

      const outDir = path.join(OUT_DIR!, fixtureName);
      fs.mkdirSync(outDir, { recursive: true });

      const element: ReactElement = m.React.createElement(m.SkillReportPDF, props);
      // eslint-disable-next-line testing-library/render-result-naming-convention -- react-pdf, not testing-library
      const pdfBuffer = await m.renderToBuffer(element);
      fs.writeFileSync(path.join(outDir, "frontend.pdf"), pdfBuffer);

      const doc = await m.constructSkillReportDocument(props);
      const docxBuffer = await m.Packer.toBuffer(doc);
      fs.writeFileSync(path.join(outDir, "frontend.docx"), docxBuffer);
    },
    60000
  );
});

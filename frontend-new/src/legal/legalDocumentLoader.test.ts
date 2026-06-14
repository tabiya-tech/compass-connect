// mute chatty console
import "src/_test_utilities/consoleMock";

import { getLegalDocument } from "src/legal/legalDocumentLoader";
import * as legalDocumentsConfig from "src/legal/legalDocumentsConfig";
import { setupFetchSpy } from "src/_test_utilities/fetchSpy";

describe("getLegalDocument", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test("returns title from frontmatter and trimmed markdown body on a successful fetch", async () => {
    // GIVEN a configured URL and a successful fetch returning markdown with a frontmatter title
    jest
      .spyOn(legalDocumentsConfig, "getLegalDocumentsConfig")
      .mockReturnValue({ termsOfUse: "/legal/terms-of-use.md" });
    const markdown = '---\ntitle: "Custom Terms"\n---\n\n# Body';
    const fetchSpy = setupFetchSpy(200, markdown, "");

    // WHEN getLegalDocument is called for that variant
    const result = await getLegalDocument("termsOfUse");

    // THEN the fetch is made against the configured URL and the parsed document is returned
    expect(fetchSpy).toHaveBeenCalledWith("/legal/terms-of-use.md");
    expect(result.title).toBe("Custom Terms");
    expect(result.markdown).toBe("# Body");
  });

  test("falls back to a per-variant default title when the markdown has no frontmatter", async () => {
    // GIVEN a configured URL and markdown without frontmatter
    jest
      .spyOn(legalDocumentsConfig, "getLegalDocumentsConfig")
      .mockReturnValue({ privacyPolicy: "/legal/privacy-policy.md" });
    const markdown = "# Privacy body\n\nSome text.";
    setupFetchSpy(200, markdown, "");

    // WHEN getLegalDocument is called
    const result = await getLegalDocument("privacyPolicy");

    // THEN the default per-variant title is used
    expect(result.title).toBe("Privacy Policy");
    expect(result.markdown).toContain("# Privacy body");
  });

  test("throws when no URL is configured for the requested variant", async () => {
    // GIVEN no configured URL for the variant
    jest.spyOn(legalDocumentsConfig, "getLegalDocumentsConfig").mockReturnValue({});

    // WHEN getLegalDocument is called THEN it rejects
    await expect(getLegalDocument("termsOfUse")).rejects.toThrow(
      /No URL configured for legal document variant: termsOfUse/
    );
  });

  test("throws when the fetch responds with a non-OK status", async () => {
    // GIVEN a configured URL and a fetch returning 404
    jest
      .spyOn(legalDocumentsConfig, "getLegalDocumentsConfig")
      .mockReturnValue({ termsOfUse: "https://partner.example/terms.md" });
    setupFetchSpy(404, "not found", "");

    // WHEN getLegalDocument is called THEN it rejects with status detail
    await expect(getLegalDocument("termsOfUse")).rejects.toThrow(/404/);
  });
});

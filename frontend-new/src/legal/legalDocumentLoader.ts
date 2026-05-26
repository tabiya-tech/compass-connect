import { parseYamlFrontmatter } from "src/knowledgeHub/parseYamlFrontmatter";
import { getLegalDocumentsConfig, LegalDocumentVariant } from "src/legal/legalDocumentsConfig";

export type { LegalDocumentVariant };

export interface LegalDocument {
  title: string;
  markdown: string;
}

const DEFAULT_TITLES: Record<LegalDocumentVariant, string> = {
  termsOfUse: "Terms of Use",
  privacyPolicy: "Privacy Policy",
};

export const getLegalDocument = async (variant: LegalDocumentVariant): Promise<LegalDocument> => {
  const url = getLegalDocumentsConfig()[variant];
  if (!url) {
    throw new Error(`No URL configured for legal document variant: ${variant}`);
  }

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load ${variant} from ${url}: ${response.status}`);
  }

  const raw = await response.text();
  const { data, content } = parseYamlFrontmatter(raw);
  // parseYamlFrontmatter returns "Untitled" when no frontmatter title is present;
  // fall back to a sensible per-variant default in that case.
  const hasExplicitTitle = typeof data.title === "string" && data.title.length > 0 && data.title !== "Untitled";
  return {
    title: hasExplicitTitle ? data.title : DEFAULT_TITLES[variant],
    markdown: content.trimStart(),
  };
};

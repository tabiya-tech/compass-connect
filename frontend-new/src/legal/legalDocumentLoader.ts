import { getProductName } from "src/envService";
import { parseYamlFrontmatter } from "src/utils/parseYamlFrontmatter";

import privacyPolicyMd from "!!raw-loader!./documents/privacy-policy.md";
import termsOfUseMd from "!!raw-loader!./documents/terms-of-use.md";
import privacyPolicyNjiraMd from "!!raw-loader!./documents/privacy-policy-njira.md";
import termsOfUseNjiraMd from "!!raw-loader!./documents/terms-of-use-njira.md";
import privacyPolicyCompassConnectMd from "!!raw-loader!./documents/privacy-policy-compass-connect.md";
import termsOfUseCompassConnectMd from "!!raw-loader!./documents/terms-of-use-compass-connect.md";

export type LegalDocumentVariant = "privacy" | "terms";

export interface LegalDocument {
  title: string;
  markdown: string;
}

const documentsByProductName: Record<string, Record<LegalDocumentVariant, string>> = {
  njila: { privacy: privacyPolicyMd, terms: termsOfUseMd },
  njira: { privacy: privacyPolicyNjiraMd, terms: termsOfUseNjiraMd },
  "compass connect": { privacy: privacyPolicyCompassConnectMd, terms: termsOfUseCompassConnectMd },
};

export const getLegalDocument = (variant: LegalDocumentVariant): LegalDocument => {
  const key = getProductName().toLowerCase();
  const registry = documentsByProductName[key] ?? documentsByProductName["njila"];
  const raw = registry[variant];
  const { data, content } = parseYamlFrontmatter(raw);
  return {
    title: data.title,
    markdown: content.trimStart(),
  };
};

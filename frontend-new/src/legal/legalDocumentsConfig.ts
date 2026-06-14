import { EnvError } from "src/error/commonErrors";
import { getLegalDocumentsEnvVar } from "src/envService";

/**
 * Reads partner-customisable legal document URLs from the FRONTEND_LEGAL_DOCUMENTS env var.
 *
 * The env var should be a JSON string with optional string-valued fields:
 * - termsOfUse: URL (absolute or site-relative) of the Terms of Use markdown document
 * - privacyPolicy: URL (absolute or site-relative) of the Privacy Policy markdown document
 *
 * Returns a `LegalDocumentsConfig` object, or an empty object if missing/invalid.
 *
 * Forward-compatibility note: a future release may extend each value to
 * `Record<Locale, string>` for per-locale documents. The current `string`-shape
 * config will continue to work unchanged.
 */
export type LegalDocumentVariant = "termsOfUse" | "privacyPolicy";

export type LegalDocumentsConfig = Partial<Record<LegalDocumentVariant, string>>;

const KNOWN_VARIANTS: LegalDocumentVariant[] = ["termsOfUse", "privacyPolicy"];

export const getLegalDocumentsConfig = (): LegalDocumentsConfig => {
  const raw = getLegalDocumentsEnvVar();
  if (!raw) return {};

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};

    const obj = parsed as Record<string, unknown>;
    return KNOWN_VARIANTS.reduce<LegalDocumentsConfig>((acc, key) => {
      const value = obj[key];
      if (typeof value === "string" && value.length > 0) {
        acc[key] = value;
      }
      return acc;
    }, {});
  } catch (e) {
    console.error(new EnvError("Error parsing FRONTEND_LEGAL_DOCUMENTS env var", e));
    return {};
  }
};

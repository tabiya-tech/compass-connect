import { type Resource, type ResourceLanguage } from "i18next";
import { Locale } from "./constants";

/**
 * Returns the resources of the locale with the text overrides of the deployment (see `getStringsOverrides`) applied.
 * Each key is dotted, as in the translation files (e.g. `home.hero.headline1`), and must name an existing text.
 * Overrides that are not text or name no existing text are skipped with a warning, so a typo never breaks the page.
 */
export function applyStringsOverrides(
  locale: Locale,
  resourceLanguage: ResourceLanguage,
  overrides: Record<string, unknown> | undefined
): ResourceLanguage {
  if (!overrides) return resourceLanguage;

  return Object.entries(overrides).reduce<ResourceLanguage>((resources, [key, text]) => {
    if (typeof text !== "string") {
      console.warn(`Text override '${key}' for ${locale} is not a string, ignoring it`);
      return resources;
    }
    const path = key.split(".");
    const currentText = path.reduce<unknown>(
      (node, segment) =>
        typeof node === "object" && node !== null ? (node as Record<string, unknown>)[segment] : undefined,
      resources
    );
    if (typeof currentText !== "string") {
      console.warn(`Text override '${key}' for ${locale} names no existing text, ignoring it`);
      return resources;
    }
    return setTextAtPath(resources, path, text);
  }, resourceLanguage);
}

// Copies the objects along the path only, so the bundled translation files are never changed.
const setTextAtPath = (resources: ResourceLanguage, [segment, ...rest]: string[], text: string): ResourceLanguage => ({
  ...resources,
  [segment]: rest.length ? setTextAtPath(resources[segment] as ResourceLanguage, rest, text) : text,
});

class ParseLocaleError extends Error {
  constructor(locale: string, cause: unknown) {
    super(`Invalid locale: ${locale}`);
    this.name = "ParseLocaleError";
    this.cause = cause;
  }
}

/**
 * Get all possible locale names for a given locale name.
 *
 * e.g.:
 * en-NG/en-ng -> en, en-ng, en-NG
 * en -> en
 */
export function getPossibleLocaleNames(locale: Locale): string[] {
  try {
    const intlLocale = new Intl.Locale(locale);
    const possibleLocaleNames = [locale, intlLocale.language, locale.toLowerCase()];

    if (intlLocale.region) {
      possibleLocaleNames.push(`${intlLocale.language}-${intlLocale.region.toUpperCase()}`);
    }

    // Remove duplicates.
    return Array.from(new Set(possibleLocaleNames));
  } catch (e) {
    // Intl.Locale has been supported in all major browsers since 2019-2020.
    // This catch block is mainly for environments where Intl.Locale is unavailable (e.g., very old browsers or non-browser environments).
    console.error(new ParseLocaleError(locale, e));
    return [locale];
  }
}

export function constructLocaleResources(locale: Locale, resourceLanguage: ResourceLanguage): Resource {
  return getPossibleLocaleNames(locale).reduce<Resource>((acc, localeName) => {
    acc[localeName] = { translation: resourceLanguage };
    return acc;
  }, {});
}

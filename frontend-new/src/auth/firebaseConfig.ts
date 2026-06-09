import "firebase/compat/auth";
import firebase from "firebase/compat/app";

import { Locale } from "src/i18n/constants";
import { getFirebaseAPIKey, getFirebaseDomain } from "src/envService";

// Get the firebase config from the environment variables
const firebaseConfig = {
  apiKey: getFirebaseAPIKey(),
  authDomain: getFirebaseDomain(),
};

// Initialize the firebase app if it hasn't been initialized yet
firebase.initializeApp(firebaseConfig);

const firebaseAuth = firebase.auth();

// Firebase only localizes its built-in email templates (password reset, email verification, ...)
// for the language codes it officially supports. Our app
// locales are region-specific (e.g., pt-MZ, ny-ZM) and are not all on that list,
// so we map each one to the closest supported Firebase language code.
// Source: https://github.com/firebase/firebaseui-web/blob/v6-archive/LANGUAGES.md
export const DEFAULT_FIREBASE_LANGUAGE = "en";

const LOCALE_TO_FIREBASE_LANGUAGE: Record<string, string> = {
  [Locale.EN_GB]: "en_gb",
  [Locale.EN_US]: "en",
  [Locale.ES_ES]: "es",
  [Locale.ES_AR]: "es_419",
  [Locale.PT_MZ]: "pt_pt",
  // sw-KE (Swahili) and ny-ZM (Nyanja) are not supported by Firebase,
  // so they fall back to DEFAULT_FIREBASE_LANGUAGE (English).
};

/**
 * Transforms an application locale (e.g. "pt-MZ") into a language code that
 * Firebase supports for localizing its emails. Falls back to English ("en")
 * when the locale has no Firebase-supported equivalent.
 */
export const toFirebaseLanguage = (locale: string): string => {
  return LOCALE_TO_FIREBASE_LANGUAGE[locale] ?? DEFAULT_FIREBASE_LANGUAGE;
};

export const updateLanguage = (language: string) => {
  firebaseAuth.languageCode = toFirebaseLanguage(language);
};

export { firebaseAuth };

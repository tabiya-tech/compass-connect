// mute chatty console
import "src/_test_utilities/consoleMock";
import firebase from "firebase/compat/app";
import { Locale } from "src/i18n/constants";

jest.mock("firebase/compat/app", () => {
  const mockAuth = { languageCode: "" };
  return {
    initializeApp: jest.fn(),
    auth: jest.fn().mockReturnValue(mockAuth),
  };
});

// mock envService so module initialization does not depend on env.js
jest.mock("src/envService", () => ({
  getFirebaseAPIKey: jest.fn().mockReturnValue("given-api-key"),
  getFirebaseDomain: jest.fn().mockReturnValue("given-domain"),
  getDefaultLocale: jest.fn().mockReturnValue("en-GB"),
}));

describe("firebaseConfig", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("toFirebaseLanguage", () => {
    test.each([
      [Locale.EN_GB, "en_gb"],
      [Locale.EN_US, "en"],
      [Locale.ES_ES, "es"],
      [Locale.ES_AR, "es_419"],
      [Locale.PT_MZ, "pt_pt"],
    ])("should map supported locale %s to firebase language %s", async (givenLocale, expectedLanguage) => {
      // GIVEN the firebaseConfig module
      const { toFirebaseLanguage } = await import("./firebaseConfig");

      // WHEN transforming a supported application locale
      const actualLanguage = toFirebaseLanguage(givenLocale);

      // THEN expect the matching firebase-supported language code
      expect(actualLanguage).toBe(expectedLanguage);
    });

    test.each([
      ["sw-KE (Swahili, not supported by firebase)", Locale.SW_KE],
      ["ny-ZM (Nyanja, not supported by firebase)", Locale.NY_ZM],
      ["a completely unknown locale", "xx-YY"],
    ])("should fall back to English for %s", async (_description, givenLocale) => {
      // GIVEN the firebaseConfig module
      const { toFirebaseLanguage, DEFAULT_FIREBASE_LANGUAGE } = await import("./firebaseConfig");

      // WHEN transforming a locale with no firebase-supported equivalent
      const actualLanguage = toFirebaseLanguage(givenLocale);

      // THEN expect the default firebase language (English)
      expect(actualLanguage).toBe(DEFAULT_FIREBASE_LANGUAGE);
      expect(actualLanguage).toBe("en");
    });
  });

  describe("updateLanguage", () => {
    test("should set the firebase auth languageCode to the transformed locale", async () => {
      // GIVEN the firebaseConfig module
      const { updateLanguage } = await import("./firebaseConfig");

      // WHEN updating the language with a supported application locale
      updateLanguage(Locale.PT_MZ);

      // THEN expect the firebase auth languageCode to be the firebase-supported code
      expect(firebase.auth().languageCode).toBe("pt_pt");
    });

    test("should set the firebase auth languageCode to English for an unsupported locale", async () => {
      // GIVEN the firebaseConfig module
      const { updateLanguage } = await import("./firebaseConfig");

      // WHEN updating the language with an unsupported application locale
      updateLanguage(Locale.NY_ZM);

      // THEN expect the firebase auth languageCode to fall back to English
      expect(firebase.auth().languageCode).toBe("en");
    });
  });
});

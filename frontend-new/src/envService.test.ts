// silence chatty console
import "src/_test_utilities/consoleMock";
import { EnvError } from "./error/commonErrors";
import {
  getBackendUrl,
  getEnv,
  getFirebaseAPIKey,
  getFirebaseDomain,
  getSentryDSN,
  getSentryEnabled,
  getSentryConfig,
  getSensitivePersonalDataRSAEncryptionKey,
  getSensitivePersonalDataRSAEncryptionKeyId,
  getSensitiveDataFields,
  ensureRequiredEnvVars,
  requiredEnvVariables,
  getTargetEnvironmentName,
  getApplicationLoginCode,
  getApplicationRegistrationCode,
  getMetricsEnabled,
  getMetricsConfig,
  getFeatures,
  getCvUploadEnabled,
  getLoginCodeDisabled,
  getRegistrationDisabled,
  getSocialAuthDisabled,
  getDefaultLocale,
  getSupportedLocales,
  getRegistrationCodeDisabled,
  getSkillsReportOutputConfigEnvVar,
  getFaqTutorialVideoUrl,
  getPartnerLogos,
} from "./envService";
import { getRandomString } from "./_test_utilities/specialCharacters";

test("getEnv should return the decoded environment variable value", () => {
  // GIVEN a key for an environment variable
  const key = "foo";
  // AND the environment variable is set to a base64 encoded string
  Object.defineProperty(window, "tabiyaConfig", {
    value: {
      foo: btoa("bar"),
    },
    writable: true,
  });
  // WHEN getEnv is called with the key
  const result = getEnv(key);
  // THEN expect the decoded URL to be returned
  expect(result).toBe("bar");
});

describe.each([
  ["FIREBASE_API_KEY", getFirebaseAPIKey],
  ["FIREBASE_AUTH_DOMAIN", getFirebaseDomain],
  ["BACKEND_URL", getBackendUrl],
  ["FRONTEND_SENTRY_DSN", getSentryDSN],
  ["FRONTEND_ENABLE_SENTRY", getSentryEnabled],
  ["FRONTEND_SENTRY_CONFIG", getSentryConfig],
  ["SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY", getSensitivePersonalDataRSAEncryptionKey],
  ["SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY_ID", getSensitivePersonalDataRSAEncryptionKeyId],
  ["FRONTEND_SENSITIVE_DATA_FIELDS", getSensitiveDataFields],
  ["TARGET_ENVIRONMENT_NAME", getTargetEnvironmentName],
  ["FRONTEND_LOGIN_CODE", getApplicationLoginCode],
  ["FRONTEND_REGISTRATION_CODE", getApplicationRegistrationCode],

  ["GLOBAL_DISABLE_LOGIN_CODE", getLoginCodeDisabled],
  ["FRONTEND_DISABLE_REGISTRATION", getRegistrationDisabled],
  ["FRONTEND_DISABLE_SOCIAL_AUTH", getSocialAuthDisabled],

  ["FRONTEND_ENABLE_METRICS", getMetricsEnabled],
  ["FRONTEND_METRICS_CONFIG", getMetricsConfig],
  ["GLOBAL_ENABLE_CV_UPLOAD", getCvUploadEnabled],
  ["FRONTEND_FEATURES", getFeatures],
  ["FRONTEND_SUPPORTED_LOCALES", getSupportedLocales],
  ["FRONTEND_DEFAULT_LOCALE", getDefaultLocale],
  ["GLOBAL_DISABLE_REGISTRATION_CODE", getRegistrationCodeDisabled],
  ["FRONTEND_SKILLS_REPORT_OUTPUT_CONFIG", getSkillsReportOutputConfigEnvVar],
  ["FRONTEND_FAQ_TUTORIAL_VIDEO_URL", getFaqTutorialVideoUrl],
])("Env Getters", (ENV_KEY, getterFn) => {
  describe(`${ENV_KEY} Getter (${getterFn.name}) tests`, () => {
    test(`getAPI should not fail if the ${ENV_KEY} is not set`, () => {
      // GIVEN the ENV_KEY environment variable is not set
      Object.defineProperty(window, "tabiyaConfig", {
        value: {},
        writable: true,
      });
      // WHEN getter Function is called
      const apiUrl = getterFn();
      // THEN expect it to return the appropriate default value
      expect(apiUrl).toBe("");
    });

    test.each([
      ["undefined", undefined],
      ["null", null],
    ])("getEnv should handle a key with a %s value gracefully", (_description: string, value) => {
      // GIVEN a key for an environment variable
      const key = "foo";
      // AND the environment variable is set to an invalid base64 encoded string
      Object.defineProperty(window, "tabiyaConfig", {
        value: {
          foo: value,
        },
        writable: true,
      });
      // WHEN getEnv is called with the key
      const result = getEnv(key);
      // THEN expect an empty string to be returned
      expect(result).toBe("");
    });

    test(`${getterFn.name} should return the correct value`, () => {
      // GIVEN the ENV_KEY environment variable is set to a base64 encoded unicode string
      const givenValue = `${ENV_KEY}_${getRandomString(10)}`;
      const utf8Bytes = new TextEncoder().encode(givenValue);
      const binary = String.fromCharCode(...utf8Bytes);

      Object.defineProperty(window, "tabiyaConfig", {
        value: {
          [ENV_KEY]: btoa(binary),
        },
        writable: true,
      });
      // WHEN getter Function is called
      const expectedValue = getterFn();
      // THEN expect it to return the decoded ENV_KEY
      expect(expectedValue).toBe(givenValue);
    });

    test("should handle base64 decoding errors gracefully", () => {
      // GIVEN the ENV KEY environment variable is set
      Object.defineProperty(window, "tabiyaConfig", {
        value: {
          [ENV_KEY]: "foo",
        },
        writable: true,
      });
      // AND the atob function will throw an error
      jest.spyOn(window, "atob").mockImplementationOnce(() => {
        throw new Error("atob error");
      });
      // WHEN getter Function is called
      const apiUrl = getterFn();
      // THEN expect it to return the appropriate default value
      expect(apiUrl).toBe("");
      // AND expect an error to have been logged
      expect(console.error).toHaveBeenCalledWith(
        new EnvError(`Error loading environment variable ${ENV_KEY}`, expect.any(Error))
      );
    });
  });
});

describe("FRONTEND_PARTNER_LOGOS Getter (getPartnerLogos) tests", () => {
  test("should return an empty array when the FRONTEND_PARTNER_LOGOS is not set", () => {
    // GIVEN the FRONTEND_PARTNER_LOGOS environment variable is not set
    Object.defineProperty(window, "tabiyaConfig", {
      value: {},
      writable: true,
    });
    // WHEN getPartnerLogos is called
    const actualPartnerLogos = getPartnerLogos();
    // THEN expect it to return an empty array
    expect(actualPartnerLogos).toEqual([]);
  });

  test("should return the decoded partner logos when the FRONTEND_PARTNER_LOGOS is set", () => {
    // GIVEN the FRONTEND_PARTNER_LOGOS environment variable is set to a base64 encoded JSON array
    const givenPartnerLogos = [
      { src: "/world-bank-logo.svg", alt: "World Bank", height: 28 },
      { src: "https://example.org/ministry.png", alt: "Ministry", height: 36, width: 120 },
    ];
    Object.defineProperty(window, "tabiyaConfig", {
      value: {
        FRONTEND_PARTNER_LOGOS: btoa(JSON.stringify(givenPartnerLogos)),
      },
      writable: true,
    });
    // WHEN getPartnerLogos is called
    const actualPartnerLogos = getPartnerLogos();
    // THEN expect it to return the decoded partner logos
    expect(actualPartnerLogos).toEqual(givenPartnerLogos);
  });

  test("should drop entries that do not have a string src", () => {
    // GIVEN the FRONTEND_PARTNER_LOGOS contains an entry without a src
    const givenPartnerLogos = [{ src: "/valid.svg", alt: "Valid" }, { alt: "missing src" }];
    Object.defineProperty(window, "tabiyaConfig", {
      value: {
        FRONTEND_PARTNER_LOGOS: btoa(JSON.stringify(givenPartnerLogos)),
      },
      writable: true,
    });
    // WHEN getPartnerLogos is called
    const actualPartnerLogos = getPartnerLogos();
    // THEN expect only the valid entry to be returned
    expect(actualPartnerLogos).toEqual([{ src: "/valid.svg", alt: "Valid" }]);
  });

  test("should return an empty array and log an error when the FRONTEND_PARTNER_LOGOS is not valid JSON", () => {
    // GIVEN the FRONTEND_PARTNER_LOGOS environment variable is set to an invalid JSON string
    Object.defineProperty(window, "tabiyaConfig", {
      value: {
        FRONTEND_PARTNER_LOGOS: btoa("not-json"),
      },
      writable: true,
    });
    // WHEN getPartnerLogos is called
    const actualPartnerLogos = getPartnerLogos();
    // THEN expect it to return an empty array
    expect(actualPartnerLogos).toEqual([]);
    // AND expect an error to have been logged
    expect(console.error).toHaveBeenCalledWith(
      new EnvError("Error parsing FRONTEND_PARTNER_LOGOS JSON", expect.any(Error))
    );
  });

  test("should return an empty array and log an error when the FRONTEND_PARTNER_LOGOS is not a JSON array", () => {
    // GIVEN the FRONTEND_PARTNER_LOGOS environment variable is set to a JSON object (not an array)
    Object.defineProperty(window, "tabiyaConfig", {
      value: {
        FRONTEND_PARTNER_LOGOS: btoa(JSON.stringify({ src: "/logo.svg" })),
      },
      writable: true,
    });
    // WHEN getPartnerLogos is called
    const actualPartnerLogos = getPartnerLogos();
    // THEN expect it to return an empty array
    expect(actualPartnerLogos).toEqual([]);
    // AND expect an error to have been logged
    expect(console.error).toHaveBeenCalledWith(new EnvError("FRONTEND_PARTNER_LOGOS must be a JSON array"));
  });
});

describe("Ensure Required Environment Variables", () => {
  it("should log a warning if any required environment variable is not set", () => {
    // GIVEN a required environment variable is not set
    Object.defineProperty(window, "tabiyaConfig", {
      value: {},
      writable: true,
    });

    // WHEN ensureRequiredEnvVars is called
    ensureRequiredEnvVars();
    // THEN expect a warning to be logged
    requiredEnvVariables.forEach((key) => {
      expect(console.warn).toHaveBeenCalledWith(`Required environment variable ${key} is not set`);
    });
  });

  it("should not log a warning if all required environment variables are set", () => {
    jest.clearAllMocks();

    // GIVEN all required environment variables are set
    Object.defineProperty(window, "tabiyaConfig", {
      value: {
        FIREBASE_API_KEY: btoa("foo"),
        FIREBASE_AUTH_DOMAIN: btoa("foo"),
        BACKEND_URL: btoa("foo"),
        TARGET_ENVIRONMENT_NAME: btoa("foo"),
        SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY: btoa("foo"),
        SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY_ID: btoa("foo"),
        FRONTEND_SUPPORTED_LOCALES: btoa("[]"),
        FRONTEND_DEFAULT_LOCALE: btoa("en-US"),
      },
      writable: true,
    });

    // WHEN ensureRequiredEnvVars is called
    ensureRequiredEnvVars();

    // THEN expect no warning to be logged
    expect(console.warn).not.toHaveBeenCalled();
  });
});

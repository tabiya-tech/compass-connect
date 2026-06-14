// mute chatty console
import "src/_test_utilities/consoleMock";

import { getLegalDocumentsConfig } from "src/legal/legalDocumentsConfig";
import * as envService from "src/envService";

describe("getLegalDocumentsConfig", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test("returns parsed config when env var contains valid JSON with both variants", () => {
    // GIVEN a valid JSON env var with both variants
    jest.spyOn(envService, "getLegalDocumentsEnvVar").mockReturnValue(
      JSON.stringify({
        termsOfUse: "/legal/terms-of-use.md",
        privacyPolicy: "/legal/privacy-policy.md",
      })
    );

    // WHEN reading the config
    const config = getLegalDocumentsConfig();

    // THEN both variants are returned
    expect(config).toEqual({
      termsOfUse: "/legal/terms-of-use.md",
      privacyPolicy: "/legal/privacy-policy.md",
    });
  });

  test("returns empty object when env var is missing/empty", () => {
    // GIVEN an empty env var
    jest.spyOn(envService, "getLegalDocumentsEnvVar").mockReturnValue("");

    // WHEN reading the config
    const config = getLegalDocumentsConfig();

    // THEN the config is empty
    expect(config).toEqual({});
  });

  test("returns empty object when env var is malformed JSON and logs an error", () => {
    // GIVEN a malformed JSON env var
    jest.spyOn(envService, "getLegalDocumentsEnvVar").mockReturnValue("{not-json");

    // WHEN reading the config
    const config = getLegalDocumentsConfig();

    // THEN the config is empty and an error is logged
    expect(config).toEqual({});
    expect(console.error).toHaveBeenCalled();
  });

  test("returns empty object when parsed value is not an object", () => {
    // GIVEN a JSON env var that is not an object
    jest.spyOn(envService, "getLegalDocumentsEnvVar").mockReturnValue(JSON.stringify("just-a-string"));

    // WHEN reading the config
    const config = getLegalDocumentsConfig();

    // THEN the config is empty
    expect(config).toEqual({});
  });

  test("filters out unknown keys and non-string values", () => {
    // GIVEN an env var with extra unknown keys and non-string values
    jest.spyOn(envService, "getLegalDocumentsEnvVar").mockReturnValue(
      JSON.stringify({
        termsOfUse: "/legal/terms-of-use.md",
        unknownKey: "/should/be/dropped.md",
        privacyPolicy: 42,
      })
    );

    // WHEN reading the config
    const config = getLegalDocumentsConfig();

    // THEN only the recognised string-valued keys remain
    expect(config).toEqual({ termsOfUse: "/legal/terms-of-use.md" });
  });

  test("only one variant is configured when the partner overrides only one", () => {
    // GIVEN an env var with only termsOfUse configured
    jest
      .spyOn(envService, "getLegalDocumentsEnvVar")
      .mockReturnValue(JSON.stringify({ termsOfUse: "https://partner.example/terms.md" }));

    // WHEN reading the config
    const config = getLegalDocumentsConfig();

    // THEN only termsOfUse is present
    expect(config).toEqual({ termsOfUse: "https://partner.example/terms.md" });
  });
});

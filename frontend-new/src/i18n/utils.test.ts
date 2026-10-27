// mute the console
import "src/_test_utilities/consoleMock";

import { Locale } from "./constants";
import * as Utils from "./utils";

describe("utils", () => {
  describe("constructLocaleResources", () => {
    test("it should return a dictionary with all possible locale names.", () => {
      // GIVEN that getPossibleLocaleNames will return a successful array
      const givenPossibleLocale = "foo";

      // AND given a locale
      const givenLocale = givenPossibleLocale as Locale;

      // AND given a resource language.
      const givenResourceLanguage = {
        "some-text": "some-value",
      };

      // WHEN the constructLocaleResources is constructed
      const actualResource = Utils.constructLocaleResources(givenLocale, givenResourceLanguage);

      // THEN the actual resource should be a dictionary with all the possible locale names as keys and the resource language as value.
      expect(actualResource).toStrictEqual({
        [givenPossibleLocale]: {
          translation: givenResourceLanguage,
        },
      });
    });
  });

  describe("getPossibleLocaleNames", () => {
    test.each([
      [Locale.EN_GB, ["en-GB", "en-gb", "en"]],
      [Locale.EN_US, ["en-US", "en-us", "en"]],
      [Locale.ES_AR, ["es-AR", "es-ar", "es"]],
      [Locale.ES_ES, ["es-ES", "es-es", "es"]],
      ["en" as Locale, ["en"]],
      ["foo-ba" as Locale, ["foo", "foo-BA", "foo-ba"]],
    ])("should return the correct locale names for %s", (givenLocale, expectedPossibleLocaleName) => {
      // GIVEN a locale name.
      // WHEN computing all the possible locale names a user can provide
      const actualPossibleLocaleNames = Utils.getPossibleLocaleNames(givenLocale);
      // THEN they should match the expected
      expect(actualPossibleLocaleNames).toIncludeSameMembers(expectedPossibleLocaleName);
    });

    test("should return the default locale if Intl.Locale.constructor throws an error", () => {
      // GIVEN Intl.Locale will throw an error because of
      //       - not supported
      //       - invalid locale
      const error = new Error("Invalid locale");
      jest.spyOn(window.Intl, "Locale").mockImplementation(() => {
        throw error;
      });

      // AND a givenLocale
      const givenLocale = Locale.EN_US;

      // WHEN computing all the possible locale names a user can provide
      const actualPossibleLocaleNames = Utils.getPossibleLocaleNames(givenLocale);

      // THEN an error should be logged.
      expect(console.error).toHaveBeenCalled();

      // AND the response should be the passed locale.
      expect(actualPossibleLocaleNames).toStrictEqual([givenLocale]);
    });
  });

  describe("applyStringsOverrides", () => {
    const givenResources = {
      home: { hero: { headline1: "Let's discover", headline2: "Your skills" } },
      common: { ok: "OK" },
    };

    beforeEach(() => {
      (console.warn as jest.Mock).mockClear();
    });

    test("should return the resources unchanged when there are no overrides", () => {
      // WHEN no overrides are applied
      const actualResources = Utils.applyStringsOverrides(Locale.EN_US, givenResources, undefined);

      // THEN the same resources are returned
      expect(actualResources).toBe(givenResources);
    });

    test("should replace the texts named by the dotted keys, leaving the others and the given resources unchanged", () => {
      // GIVEN overrides of a nested and a top-level text
      const givenOverrides = { "home.hero.headline1": "Discover", "common.ok": "Fine" };

      // WHEN the overrides are applied
      const actualResources = Utils.applyStringsOverrides(Locale.EN_US, givenResources, givenOverrides);

      // THEN the named texts are replaced and the others kept
      expect(actualResources).toEqual({
        home: { hero: { headline1: "Discover", headline2: "Your skills" } },
        common: { ok: "Fine" },
      });
      // AND the given resources are not changed
      expect(givenResources.home.hero.headline1).toBe("Let's discover");
      // AND nothing is warned about
      expect(console.warn).not.toHaveBeenCalled();
    });

    test.each([
      ["names no existing text", { "home.hero.typo": "foo" }],
      ["names a group of texts, not a text", { "home.hero": "foo" }],
      ["is not a string", { "home.hero.headline1": 42 }],
    ])("should skip an override that %s, with a warning", (_description, givenOverrides) => {
      // WHEN the override is applied
      const actualResources = Utils.applyStringsOverrides(Locale.EN_US, givenResources, givenOverrides);

      // THEN the resources are unchanged
      expect(actualResources).toEqual(givenResources);
      // AND a warning is logged
      expect(console.warn).toHaveBeenCalledTimes(1);
    });
  });
});

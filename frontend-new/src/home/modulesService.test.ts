// mute the console
import "src/_test_utilities/consoleMock";

import * as EnvServiceModule from "src/envService";
import { getEnabledModules, isModuleEnabled, ModuleId } from "src/home/modulesService";
import { useNextModule } from "src/home/useNextModule";

const ALL_MODULE_IDS: ModuleId[] = [
  "skills_discovery",
  "career_explorer",
  "job_readiness",
  "knowledge_hub",
  "job_matching",
  "faq",
];

describe("modulesService", () => {
  beforeEach(() => {
    (console.warn as jest.Mock).mockClear();
  });

  afterEach(() => {
    (EnvServiceModule.getDisabledModules as jest.Mock).mockRestore?.();
  });

  test("should return every module when no module is disabled", () => {
    // GIVEN no module is disabled
    jest.spyOn(EnvServiceModule, "getDisabledModules").mockReturnValue([]);

    // WHEN the enabled modules are requested
    const actualModules = getEnabledModules();

    // THEN every module is returned, in order
    expect(actualModules.map((m) => m.id)).toEqual(ALL_MODULE_IDS);
    // AND every module is enabled
    ALL_MODULE_IDS.forEach((id) => expect(isModuleEnabled(id)).toBe(true));
    // AND nothing is logged
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should leave out the disabled modules", () => {
    // GIVEN some modules are disabled
    jest.spyOn(EnvServiceModule, "getDisabledModules").mockReturnValue(["career_explorer", "job_matching"]);

    // WHEN the enabled modules are requested
    const actualModules = getEnabledModules();

    // THEN the disabled modules are not returned
    expect(actualModules.map((m) => m.id)).toEqual(["skills_discovery", "job_readiness", "knowledge_hub", "faq"]);
    // AND they are not enabled
    expect(isModuleEnabled("career_explorer")).toBe(false);
    expect(isModuleEnabled("job_matching")).toBe(false);
    expect(isModuleEnabled("skills_discovery")).toBe(true);
  });

  test("should ignore an unknown module id, warning about it once", () => {
    // GIVEN an unknown module id is disabled
    jest.spyOn(EnvServiceModule, "getDisabledModules").mockReturnValue(["foo_module"]);

    // WHEN the enabled modules are requested twice
    const actualModules = getEnabledModules();
    getEnabledModules();

    // THEN every module is returned
    expect(actualModules.map((m) => m.id)).toEqual(ALL_MODULE_IDS);
    // AND the unknown id is warned about once
    expect(console.warn).toHaveBeenCalledTimes(1);
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining("foo_module"));
  });

  describe("useNextModule", () => {
    test("should return the next module when it is enabled", () => {
      // GIVEN no module is disabled
      jest.spyOn(EnvServiceModule, "getDisabledModules").mockReturnValue([]);

      // WHEN the next module of skills discovery is requested
      const actualNextModule = useNextModule("skills_discovery");

      // THEN the career explorer is returned
      expect(actualNextModule?.id).toBe("career_explorer");
    });

    test("should return null when the next module is disabled", () => {
      // GIVEN the career explorer is disabled
      jest.spyOn(EnvServiceModule, "getDisabledModules").mockReturnValue(["career_explorer"]);

      // WHEN the next module of skills discovery is requested
      const actualNextModule = useNextModule("skills_discovery");

      // THEN no next module is suggested
      expect(actualNextModule).toBeNull();
    });
  });
});

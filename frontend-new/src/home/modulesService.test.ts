// mute the console
import "src/_test_utilities/consoleMock";

import * as EnvServiceModule from "src/envService";
import { getEnabledModules, isModuleEnabled, ModuleId } from "src/home/modulesService";
import { useNextModule } from "src/home/useNextModule";

const ALL_MODULE_IDS: ModuleId[] = [
  ModuleId.SKILLS_DISCOVERY,
  ModuleId.CAREER_EXPLORER,
  ModuleId.JOB_READINESS,
  ModuleId.KNOWLEDGE_HUB,
  ModuleId.JOB_MATCHING,
  ModuleId.FAQ,
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
    jest
      .spyOn(EnvServiceModule, "getDisabledModules")
      .mockReturnValue([ModuleId.CAREER_EXPLORER, ModuleId.JOB_MATCHING]);

    // WHEN the enabled modules are requested
    const actualModules = getEnabledModules();

    // THEN the disabled modules are not returned
    expect(actualModules.map((m) => m.id)).toEqual([
      ModuleId.SKILLS_DISCOVERY,
      ModuleId.JOB_READINESS,
      ModuleId.KNOWLEDGE_HUB,
      ModuleId.FAQ,
    ]);
    // AND they are not enabled
    expect(isModuleEnabled(ModuleId.CAREER_EXPLORER)).toBe(false);
    expect(isModuleEnabled(ModuleId.JOB_MATCHING)).toBe(false);
    expect(isModuleEnabled(ModuleId.SKILLS_DISCOVERY)).toBe(true);
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
      const actualNextModule = useNextModule(ModuleId.SKILLS_DISCOVERY);

      // THEN the career explorer is returned
      expect(actualNextModule?.id).toBe(ModuleId.CAREER_EXPLORER);
    });

    test("should return null when the next module is disabled", () => {
      // GIVEN the career explorer is disabled
      jest.spyOn(EnvServiceModule, "getDisabledModules").mockReturnValue([ModuleId.CAREER_EXPLORER]);

      // WHEN the next module of skills discovery is requested
      const actualNextModule = useNextModule(ModuleId.SKILLS_DISCOVERY);

      // THEN no next module is suggested
      expect(actualNextModule).toBeNull();
    });
  });
});

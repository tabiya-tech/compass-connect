import { getEnabledModules, PlatformModuleConfig, PlatformModule } from "./modulesService";

/**
 * Given a module id, returns the next top-level module to suggest
 * based on the `nextModuleId` field configured in modulesService.
 *
 * Returns null if no handoff is configured for the given module.
 */
export const useNextModule = (moduleId: PlatformModule): PlatformModuleConfig | null => {
  const modules = getEnabledModules();
  const current = modules.find((m) => m.id === moduleId);
  if (!current?.nextModuleId) return null;
  return modules.find((m) => m.id === current.nextModuleId) ?? null;
};

import { routerPaths } from "src/app/routerPaths";
import { getDisabledModules } from "src/envService";

/**
 * The ids of the modules, also used in `FRONTEND_DISABLED_MODULES` to hide them.
 */
export enum ModuleId {
  SKILLS_DISCOVERY = "skills_discovery",
  CAREER_EXPLORER = "career_explorer",
  JOB_READINESS = "job_readiness",
  KNOWLEDGE_HUB = "knowledge_hub",
  JOB_MATCHING = "job_matching",
  FAQ = "faq",
}

export interface Module {
  id: ModuleId;
  labelKey: string;
  descriptionKey: string;
  route: string;
  disabled?: boolean;
  /**
   * The id of the next top-level module to suggest when this module completes.
   * Leave undefined if there is no automatic handoff.
   */
  nextModuleId?: ModuleId;
}

/**
 * The default set of modules that are always available on the Home page.
 */
const DEFAULT_MODULES: Module[] = [
  {
    id: ModuleId.SKILLS_DISCOVERY,
    labelKey: "home.modules.skillsDiscovery",
    descriptionKey: "home.modules.skillsDiscoveryDesc",
    route: routerPaths.SKILLS_INTERESTS,
    nextModuleId: ModuleId.CAREER_EXPLORER,
  },
  {
    id: ModuleId.CAREER_EXPLORER,
    labelKey: "home.modules.careerExplorer",
    descriptionKey: "home.modules.careerExplorerDesc",
    route: routerPaths.CAREER_EXPLORER,
  },
  {
    id: ModuleId.JOB_READINESS,
    labelKey: "home.modules.jobReadiness",
    descriptionKey: "home.modules.jobReadinessDesc",
    route: routerPaths.CAREER_READINESS,
    nextModuleId: ModuleId.KNOWLEDGE_HUB,
  },
  {
    id: ModuleId.KNOWLEDGE_HUB,
    labelKey: "home.modules.knowledgeHub",
    descriptionKey: "home.modules.knowledgeHubDesc",
    route: routerPaths.KNOWLEDGE_HUB,
  },
  {
    id: ModuleId.JOB_MATCHING,
    labelKey: "home.modules.jobMatching",
    descriptionKey: "home.modules.jobMatchingDesc",
    route: routerPaths.JOB_MATCHING,
  },
  {
    // the help page: not a step of the journey, so no module hands off to it
    id: ModuleId.FAQ,
    labelKey: "nav.needHelp",
    descriptionKey: "faq.lede",
    route: routerPaths.FAQ,
  },
];

// Unknown ids already warned about, so a misconfigured deployment logs each one once and not on every render.
const warnedUnknownModuleIds = new Set<string>();

/**
 * Gets the list of enabled modules: the default set of modules, without the ones disabled for this deployment
 * (`FRONTEND_DISABLED_MODULES`).
 */
export const getEnabledModules = (): Module[] => {
  const disabledModuleIds = getDisabledModules();
  disabledModuleIds
    .filter((id) => !DEFAULT_MODULES.some((module) => module.id === id) && !warnedUnknownModuleIds.has(id))
    .forEach((id) => {
      warnedUnknownModuleIds.add(id);
      console.warn(`Unknown module id '${id}' in FRONTEND_DISABLED_MODULES, ignoring it`);
    });
  return DEFAULT_MODULES.filter((module) => !disabledModuleIds.includes(module.id));
};

/**
 * Whether the module is enabled for this deployment. Disabled modules have no routes and no links to them.
 */
export const isModuleEnabled = (moduleId: ModuleId): boolean => {
  return getEnabledModules().some((module) => module.id === moduleId);
};

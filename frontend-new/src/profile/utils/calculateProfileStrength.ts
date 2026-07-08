import { ConversationPhase } from "src/chat/chatProgressbar/types";
import { Experience, WorkType } from "src/experiences/experienceService/experiences.types";
import type { ModuleSummary } from "src/careerReadiness/types";
import type { UserSectorEngagementItem } from "src/careerExplorer/services/CareerExplorerService";

export interface ProfileStrengthInput {
  phase: ConversationPhase | null;
  phaseCurrent: number | null;
  phaseTotal: number | null;
  totalExperiences: number;
  exploredExperiences: number;
  experiences: Experience[];
  modules: ModuleSummary[];
  sectors: UserSectorEngagementItem[];
}

export interface ProfileStrengthComponent {
  points: number;
  max: number;
}

export interface ProfileStrengthBreakdown {
  experienceCollection: ProfileStrengthComponent;
  skillsDiscovery: ProfileStrengthComponent;
  preferences: ProfileStrengthComponent;
  careerReadiness: ProfileStrengthComponent;
  careerExplorer: ProfileStrengthComponent;
  overall: number;
}

// Component weights, summing to 100.
export const EXPERIENCE_COLLECTION_MAX = 20;
export const SKILLS_DISCOVERY_MAX = 25;
export const PREFERENCES_MAX = 20;
export const CAREER_READINESS_MAX = 30;
export const CAREER_EXPLORER_MAX = 5;

const POINTS_PER_COMPLETED_MODULE = 5; // per completed career-readiness module (6 modules -> 30)
const WORK_TYPE_DONE_POINTS = 10; // work-type question finished
const WORK_TYPE_PARTIAL_POINTS = 5; // still collecting, with >= 1 of that type collected
const PAID_WORK_TYPE_POSITION = 1; // paid work is asked first during a collection

// Conversation order
const PHASE_SEQUENCE = [
  ConversationPhase.INITIALIZING,
  ConversationPhase.INTRO,
  ConversationPhase.COLLECT_EXPERIENCES,
  ConversationPhase.DIVE_IN,
  ConversationPhase.PREFERENCE_ELICITATION,
  ConversationPhase.RECOMMENDATION,
  ConversationPhase.ENDED,
];

// True once the conversation has reached `target` or a later phase.
const hasReachedPhase = (phase: ConversationPhase | null, target: ConversationPhase): boolean => {
  if (phase === null) {
    return false;
  }
  const current = PHASE_SEQUENCE.indexOf(phase);
  return current !== -1 && current >= PHASE_SEQUENCE.indexOf(target);
};

// Full points once the work-type question is done, half for >= 1 collected while still collecting.
const getWorkTypePoints = (done: boolean, collectedCount: number): number => {
  if (done) {
    return WORK_TYPE_DONE_POINTS;
  }
  if (collectedCount >= 1) {
    return WORK_TYPE_PARTIAL_POINTS;
  }
  return 0;
};

// Profile strength (0-100): sum of five weighted components.
export const calculateProfileStrength = (input: ProfileStrengthInput): ProfileStrengthBreakdown => {
  const { phase, phaseCurrent, phaseTotal, totalExperiences, exploredExperiences, experiences, modules, sectors } =
    input;

  const isPastCollect = hasReachedPhase(phase, ConversationPhase.DIVE_IN);
  const isCollecting = phase === ConversationPhase.COLLECT_EXPERIENCES;

  const hasMovedPastPaidQuestion = isCollecting && phaseCurrent !== null && phaseCurrent > PAID_WORK_TYPE_POSITION;
  const paidDone = isPastCollect || hasMovedPastPaidQuestion;
  const unpaidDone = isPastCollect;

  const paidExperiencesCount = experiences.filter(
    (experience) => experience.work_type === WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT
  ).length;
  const unpaidExperiencesCount = experiences.filter(
    (experience) =>
      experience.work_type === WorkType.FORMAL_SECTOR_UNPAID_TRAINEE_WORK ||
      experience.work_type === WorkType.UNSEEN_UNPAID
  ).length;

  const paidPoints = getWorkTypePoints(paidDone, paidExperiencesCount);
  const unpaidPoints = getWorkTypePoints(unpaidDone, unpaidExperiencesCount);

  const experienceCollectionPoints = paidPoints + unpaidPoints;

  const skillsDiscoveryPoints =
    totalExperiences > 0 ? (exploredExperiences / totalExperiences) * SKILLS_DISCOVERY_MAX : 0;

  // Full once the recommendation is reached; otherwise proportional to elicitation sub-progress.
  let preferencesPoints = 0;
  if (hasReachedPhase(phase, ConversationPhase.RECOMMENDATION)) {
    preferencesPoints = PREFERENCES_MAX;
  } else if (
    phase === ConversationPhase.PREFERENCE_ELICITATION &&
    phaseCurrent !== null &&
    phaseTotal !== null &&
    phaseTotal > 0
  ) {
    preferencesPoints = Math.min(phaseCurrent / phaseTotal, 1) * PREFERENCES_MAX;
  }

  const completedModules = modules.filter((module) => module.status === "COMPLETED").length;
  const careerReadinessPoints = Math.min(completedModules * POINTS_PER_COMPLETED_MODULE, CAREER_READINESS_MAX);

  const totalInquiries = sectors.reduce((sum, sector) => sum + sector.inquiry_count, 0);
  const careerExplorerPoints = totalInquiries >= 1 ? CAREER_EXPLORER_MAX : 0;

  const overall = Math.max(
    0,
    Math.min(
      100,
      Math.round(
        experienceCollectionPoints +
          skillsDiscoveryPoints +
          preferencesPoints +
          careerReadinessPoints +
          careerExplorerPoints
      )
    )
  );

  return {
    experienceCollection: { points: experienceCollectionPoints, max: EXPERIENCE_COLLECTION_MAX },
    skillsDiscovery: { points: skillsDiscoveryPoints, max: SKILLS_DISCOVERY_MAX },
    preferences: { points: preferencesPoints, max: PREFERENCES_MAX },
    careerReadiness: { points: careerReadinessPoints, max: CAREER_READINESS_MAX },
    careerExplorer: { points: careerExplorerPoints, max: CAREER_EXPLORER_MAX },
    overall,
  };
};

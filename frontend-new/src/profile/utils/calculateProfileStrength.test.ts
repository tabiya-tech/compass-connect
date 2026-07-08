import { calculateProfileStrength, ProfileStrengthInput } from "./calculateProfileStrength";
import { ConversationPhase } from "src/chat/chatProgressbar/types";
import { DiveInPhase, Experience, WorkType } from "src/experiences/experienceService/experiences.types";
import type { ModuleSummary, ModuleStatus } from "src/careerReadiness/types";
import type { UserSectorEngagementItem } from "src/careerExplorer/services/CareerExplorerService";

const getModule = (status: ModuleStatus, index: number = 0): ModuleSummary => ({
  id: `module-${index}`,
  title: `Module ${index}`,
  description: "",
  icon: "",
  status,
  sort_order: index + 1,
  input_placeholder: "",
  active_conversation_id: null,
  topics: [],
});

const getExperience = (workType: WorkType | null): Experience => ({
  UUID: `experience-${workType ?? "none"}`,
  timeline: { start: "", end: "" },
  experience_title: "",
  company: "",
  location: "",
  work_type: workType,
  top_skills: [],
  remaining_skills: [],
  summary: null,
  exploration_phase: DiveInPhase.NOT_STARTED,
});

const paidExperience = getExperience(WorkType.FORMAL_SECTOR_WAGED_EMPLOYMENT);
const unpaidExperience = getExperience(WorkType.FORMAL_SECTOR_UNPAID_TRAINEE_WORK);

const getSector = (inquiryCount: number): UserSectorEngagementItem => ({
  sector_name: "Agriculture",
  is_priority: false,
  inquiry_count: inquiryCount,
  last_asked_at: null,
});

const getDefaultInput = (overrides: Partial<ProfileStrengthInput> = {}): ProfileStrengthInput => ({
  phase: null,
  phaseCurrent: null,
  phaseTotal: null,
  totalExperiences: 0,
  exploredExperiences: 0,
  experiences: [],
  modules: [],
  sectors: [],
  ...overrides,
});

describe("calculateProfileStrength", () => {
  describe("experience collection component (max 20)", () => {
    test("should give 0 points when there is no conversation and no experiences", () => {
      // GIVEN a user with no conversation phase and no experiences
      const input = getDefaultInput();

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the experience collection component is 0
      expect(breakdown.experienceCollection).toEqual({ points: 0, max: 20 });
      expect(breakdown.overall).toBe(0);
    });

    test("should give 5 points per work type with at least one collected experience while still collecting the first work type", () => {
      // GIVEN a conversation still on the paid work question (current=1) with 1 paid and 1 unpaid experience
      const input = getDefaultInput({
        phase: ConversationPhase.COLLECT_EXPERIENCES,
        phaseCurrent: 1,
        totalExperiences: 2,
        experiences: [paidExperience, unpaidExperience],
      });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN both work types get partial credit (5 + 5)
      expect(breakdown.experienceCollection).toEqual({ points: 10, max: 20 });
    });

    test("should give 10 points for paid once the conversation moved to the second work type", () => {
      // GIVEN a conversation on the unpaid work question (current=2) with no experiences collected
      const input = getDefaultInput({
        phase: ConversationPhase.COLLECT_EXPERIENCES,
        phaseCurrent: 2,
      });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN paid is done (10) even without paid experiences, unpaid is not started (0)
      expect(breakdown.experienceCollection).toEqual({ points: 10, max: 20 });
    });

    test("should give partial unpaid credit while paid is done and unpaid is being collected", () => {
      // GIVEN a conversation on the unpaid work question with 1 unpaid experience collected
      const input = getDefaultInput({
        phase: ConversationPhase.COLLECT_EXPERIENCES,
        phaseCurrent: 2,
        totalExperiences: 1,
        experiences: [unpaidExperience],
      });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN paid is done (10) and unpaid gets partial credit (5)
      expect(breakdown.experienceCollection).toEqual({ points: 15, max: 20 });
    });

    test.each([
      ConversationPhase.DIVE_IN,
      ConversationPhase.PREFERENCE_ELICITATION,
      ConversationPhase.RECOMMENDATION,
      ConversationPhase.ENDED,
    ])("should give the full 20 points when the phase is %s, even with no experiences", (phase) => {
      // GIVEN a conversation past the collection phase with no experiences (user said no to both)
      const input = getDefaultInput({ phase });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the full experience collection points are awarded
      expect(breakdown.experienceCollection).toEqual({ points: 20, max: 20 });
    });

    test.each([ConversationPhase.INTRO, ConversationPhase.INITIALIZING, ConversationPhase.UNKNOWN])(
      "should treat phase %s as not past collection",
      (phase) => {
        // GIVEN a conversation that has not reached the collection phase, with 1 paid experience
        const input = getDefaultInput({ phase, totalExperiences: 1, experiences: [paidExperience] });

        // WHEN the profile strength is calculated
        const breakdown = calculateProfileStrength(input);

        // THEN only the paid partial credit is awarded
        expect(breakdown.experienceCollection).toEqual({ points: 5, max: 20 });
      }
    );

    test("should not treat phaseCurrent as meaningful outside COLLECT_EXPERIENCES", () => {
      // GIVEN an INTRO phase with a (stale) phaseCurrent of 2
      const input = getDefaultInput({ phase: ConversationPhase.INTRO, phaseCurrent: 2 });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN no experience collection points are awarded
      expect(breakdown.experienceCollection).toEqual({ points: 0, max: 20 });
    });
  });

  describe("skills discovery component (max 25)", () => {
    test("should give 0 points when there are no experiences", () => {
      // GIVEN no collected experiences
      const input = getDefaultInput({ totalExperiences: 0, exploredExperiences: 0 });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the skills discovery component is 0
      expect(breakdown.skillsDiscovery).toEqual({ points: 0, max: 25 });
    });

    test("should scale points with the share of explored experiences", () => {
      // GIVEN 2 of 4 experiences explored
      const input = getDefaultInput({ totalExperiences: 4, exploredExperiences: 2 });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN half of the skills discovery points are awarded
      expect(breakdown.skillsDiscovery).toEqual({ points: 12.5, max: 25 });
    });

    test("should give the full 25 points when all experiences are explored", () => {
      // GIVEN all experiences explored
      const input = getDefaultInput({ totalExperiences: 3, exploredExperiences: 3 });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the full skills discovery points are awarded
      expect(breakdown.skillsDiscovery).toEqual({ points: 25, max: 25 });
    });
  });

  describe("preferences component (max 20)", () => {
    test.each([ConversationPhase.RECOMMENDATION, ConversationPhase.ENDED])(
      "should give 20 points when the phase is %s",
      (phase) => {
        // GIVEN a conversation past preference elicitation
        const input = getDefaultInput({ phase });

        // WHEN the profile strength is calculated
        const breakdown = calculateProfileStrength(input);

        // THEN the full preferences points are awarded
        expect(breakdown.preferences).toEqual({ points: 20, max: 20 });
      }
    );

    test.each([null, ConversationPhase.INTRO, ConversationPhase.COLLECT_EXPERIENCES, ConversationPhase.DIVE_IN])(
      "should give 0 points when the phase is %s",
      (phase) => {
        // GIVEN a conversation that has not reached preference elicitation
        const input = getDefaultInput({ phase });

        // WHEN the profile strength is calculated
        const breakdown = calculateProfileStrength(input);

        // THEN no preferences points are awarded
        expect(breakdown.preferences).toEqual({ points: 0, max: 20 });
      }
    );

    test("should give proportional credit while preference elicitation is in progress", () => {
      // GIVEN a preference elicitation flow halfway through (3 of 6 steps)
      const input = getDefaultInput({
        phase: ConversationPhase.PREFERENCE_ELICITATION,
        phaseCurrent: 3,
        phaseTotal: 6,
      });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN half of the preferences points are awarded
      expect(breakdown.preferences).toEqual({ points: 10, max: 20 });
    });

    test("should cap the proportional preferences credit at 20 points", () => {
      // GIVEN a preference elicitation sub-progress reporting more steps than the total
      const input = getDefaultInput({
        phase: ConversationPhase.PREFERENCE_ELICITATION,
        phaseCurrent: 8,
        phaseTotal: 6,
      });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the preferences points are capped at the maximum
      expect(breakdown.preferences).toEqual({ points: 20, max: 20 });
    });

    test("should give 0 points during preference elicitation when the sub-progress is unavailable", () => {
      // GIVEN a preference elicitation phase without current/total counters
      const input = getDefaultInput({ phase: ConversationPhase.PREFERENCE_ELICITATION });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN no preferences points are awarded
      expect(breakdown.preferences).toEqual({ points: 0, max: 20 });
    });
  });

  describe("career readiness component (max 30)", () => {
    test("should give 5 points per completed module", () => {
      // GIVEN 2 completed modules out of 6
      const modules = [
        getModule("COMPLETED", 0),
        getModule("COMPLETED", 1),
        getModule("IN_PROGRESS", 2),
        getModule("NOT_STARTED", 3),
        getModule("NOT_STARTED", 4),
        getModule("NOT_STARTED", 5),
      ];
      const input = getDefaultInput({ modules });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN 10 career readiness points are awarded
      expect(breakdown.careerReadiness).toEqual({ points: 10, max: 30 });
    });

    test("should give the full 30 points when all 6 modules are completed", () => {
      // GIVEN 6 completed modules
      const modules = Array.from({ length: 6 }, (_, i) => getModule("COMPLETED", i));
      const input = getDefaultInput({ modules });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the full career readiness points are awarded
      expect(breakdown.careerReadiness).toEqual({ points: 30, max: 30 });
    });

    test("should cap the points at 30 even with more than 6 completed modules", () => {
      // GIVEN 7 completed modules
      const modules = Array.from({ length: 7 }, (_, i) => getModule("COMPLETED", i));
      const input = getDefaultInput({ modules });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the career readiness points are capped at 30
      expect(breakdown.careerReadiness).toEqual({ points: 30, max: 30 });
    });
  });

  describe("career explorer component (max 5)", () => {
    test("should give 0 points when the user asked no sector questions", () => {
      // GIVEN sectors with no inquiries
      const input = getDefaultInput({ sectors: [getSector(0)] });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN no career explorer points are awarded
      expect(breakdown.careerExplorer).toEqual({ points: 0, max: 5 });
    });

    test("should give 5 points when the user asked at least one sector question", () => {
      // GIVEN a sector with one inquiry
      const input = getDefaultInput({ sectors: [getSector(1)] });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the full career explorer points are awarded
      expect(breakdown.careerExplorer).toEqual({ points: 5, max: 5 });
    });
  });

  describe("overall", () => {
    test("should sum to 100 when everything is complete", () => {
      // GIVEN a fully complete profile
      const input = getDefaultInput({
        phase: ConversationPhase.ENDED,
        totalExperiences: 3,
        exploredExperiences: 3,
        experiences: [paidExperience, unpaidExperience],
        modules: Array.from({ length: 6 }, (_, i) => getModule("COMPLETED", i)),
        sectors: [getSector(2)],
      });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the overall strength is 100
      expect(breakdown.overall).toBe(100);
    });

    test("should round the overall to the nearest integer", () => {
      // GIVEN a skills discovery ratio producing a fractional score (1/3 of 25 ≈ 8.33)
      const input = getDefaultInput({ totalExperiences: 3, exploredExperiences: 1 });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN the overall is rounded
      expect(breakdown.overall).toBe(8);
    });

    test("should sum a mid-journey profile correctly", () => {
      // GIVEN a user still collecting unpaid experiences (paid done), 1 of 2 experiences explored,
      // 1 completed module, and career explorer started
      const input = getDefaultInput({
        phase: ConversationPhase.COLLECT_EXPERIENCES,
        phaseCurrent: 2,
        totalExperiences: 2,
        exploredExperiences: 1,
        experiences: [paidExperience, unpaidExperience],
        modules: [getModule("COMPLETED", 0)],
        sectors: [getSector(1)],
      });

      // WHEN the profile strength is calculated
      const breakdown = calculateProfileStrength(input);

      // THEN each component contributes as expected: 15 + 12.5 + 0 + 5 + 5 = 37.5 → 38
      expect(breakdown.experienceCollection.points).toBe(15);
      expect(breakdown.skillsDiscovery.points).toBe(12.5);
      expect(breakdown.preferences.points).toBe(0);
      expect(breakdown.careerReadiness.points).toBe(5);
      expect(breakdown.careerExplorer.points).toBe(5);
      expect(breakdown.overall).toBe(38);
    });
  });
});

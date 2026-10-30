import "src/_test_utilities/consoleMock";
import "src/_test_utilities/envServiceMock";

import React from "react";
import { render, screen } from "src/_test_utilities/test-utils";
import { Profile, DATA_TEST_ID, ProfileProps } from "./Profile";

// Mock all sub-components
jest.mock("./components/SecurityCard/SecurityCard", () => ({
  SecurityCard: jest.fn(({ email, isLoading }) => (
    <div data-testid="security-card">
      SecurityCard: {email || "null"}, {isLoading ? "loading" : "loaded"}
    </div>
  )),
}));

jest.mock("./components/PreferencesCard/PreferencesCard", () => ({
  PreferencesCard: jest.fn(({ language, isLoading }) => (
    <div data-testid="preferences-card">
      PreferencesCard: {language || "null"}, {isLoading ? "loading" : "loaded"}
    </div>
  )),
}));

jest.mock("./components/ProfileCard/ProfileCard", () => ({
  ProfileCard: jest.fn(({ name, location, school, program, year, isLoading }) => (
    <div data-testid="profile-card">
      ProfileCard: {name || "null"}, {location || "null"}, {school || "null"}, {program || "null"}, {year || "null"},{" "}
      {isLoading ? "loading" : "loaded"}
    </div>
  )),
}));

jest.mock("src/careerReadiness/components/CareerReadinessProgressBanner/CareerReadinessProgressBanner", () =>
  jest.fn(({ modules }) => (
    <div data-testid="career-readiness-progress-banner">CareerReadinessProgressBanner: {modules.length} modules</div>
  ))
);

jest.mock("./components/SkillsDiscoveredCard/SkillsDiscoveredCard", () => ({
  SkillsDiscoveredCard: jest.fn(({ skills, isLoading }) => (
    <div data-testid="skills-discovered-card">
      SkillsDiscoveredCard: {skills.length} skills, {isLoading ? "loading" : "loaded"}
    </div>
  )),
}));

// Import mocked components for assertions
import { SecurityCard } from "./components/SecurityCard/SecurityCard";
import { PreferencesCard } from "./components/PreferencesCard/PreferencesCard";
import { ProfileCard } from "./components/ProfileCard/ProfileCard";
import { SkillsDiscoveredCard } from "./components/SkillsDiscoveredCard/SkillsDiscoveredCard";
import CareerReadinessProgressBanner from "src/careerReadiness/components/CareerReadinessProgressBanner/CareerReadinessProgressBanner";
import type { ModuleSummary } from "src/careerReadiness/types";
import { getDisabledModules } from "src/envService";
import { DATA_TEST_ID as CAREER_EXPLORER_CARD_DATA_TEST_ID } from "./components/CareerExplorerCard/CareerExplorerCard";
import { DATA_TEST_ID as MODULE_PROGRESS_CARD_DATA_TEST_ID } from "./components/ModuleProgressCard/ModuleProgressCard";

const makeModule = (id: string, status: ModuleSummary["status"]): ModuleSummary => ({
  id,
  title: id,
  description: "",
  icon: "",
  status,
  sort_order: 0,
  input_placeholder: "",
  active_conversation_id: null,
  topics: [],
});

// Helper function to create default props
const getDefaultProps = (overrides?: Partial<ProfileProps>): ProfileProps => ({
  email: null,
  language: null,
  termsAcceptedDate: null,
  name: null,
  location: null,
  school: null,
  program: null,
  year: null,
  skills: [],
  educationSkills: [],
  totalExperiences: 0,
  exploredExperiences: 0,
  experiences: [],
  modules: [],
  conversationPhase: null,
  careerExplorerSectors: [],
  isLoadingSecurity: false,
  isLoadingPreferences: false,
  isLoadingProfile: false,
  isLoadingSkills: false,
  isLoadingProgress: false,
  isLoadingCareerExplorer: false,
  ...overrides,
});

describe("Profile Component", () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
    (getDisabledModules as jest.Mock).mockReturnValue([]);
  });

  describe("Rendering", () => {
    test("should render all profile sections with correct props", () => {
      // GIVEN complete profile data
      const givenProps = getDefaultProps({
        name: "John Doe",
        email: "john.doe@example.com",
        termsAcceptedDate: new Date("2024-01-15"),
        language: "en",
        location: "baz",
        school: "bar",
        program: "foo",
        year: "2024",
        skills: [],
        modules: [makeModule("skills_discovery", "COMPLETED"), makeModule("career_discovery", "IN_PROGRESS")],
      });

      // WHEN the Profile component is rendered
      render(<Profile {...givenProps} />);

      // THEN the profile content container is in the document
      const contentContainer = screen.getByTestId(DATA_TEST_ID.PROFILE_CONTENT);
      expect(contentContainer).toBeInTheDocument();

      // AND ProfileCard is called with correct props
      expect(ProfileCard).toHaveBeenCalledWith(
        {
          name: "John Doe",
          location: "baz",
          school: "bar",
          program: "foo",
          year: "2024",
          isLoading: false,
        },
        expect.anything()
      );

      // AND CareerReadinessProgressBanner is called with correct props
      expect(CareerReadinessProgressBanner).toHaveBeenCalledWith(
        {
          modules: [makeModule("skills_discovery", "COMPLETED"), makeModule("career_discovery", "IN_PROGRESS")],
        },
        expect.anything()
      );

      // AND SkillsDiscoveredCard is called with correct props
      expect(SkillsDiscoveredCard).toHaveBeenCalledWith(
        {
          skills: [],
          educationSkills: [],
          program: "foo",
          school: "bar",
          isLoading: false,
        },
        expect.anything()
      );

      // AND SecurityCard is called with correct props
      expect(SecurityCard).toHaveBeenCalledWith(
        {
          email: "john.doe@example.com",
          isLoading: false,
        },
        expect.anything()
      );

      // AND PreferencesCard is called with correct props
      expect(PreferencesCard).toHaveBeenCalledWith(
        {
          language: "en",
          acceptedTcDate: new Date("2024-01-15"),
          isLoading: false,
        },
        expect.anything()
      );

      // AND the content should match the snapshot
      expect(contentContainer).toMatchSnapshot();
    });

    test("should render with null data showing 'Not available'", () => {
      // GIVEN profile data with all null values
      const givenProps = getDefaultProps();

      // WHEN the Profile component is rendered
      render(<Profile {...givenProps} />);

      // THEN the profile content is rendered
      const contentContainer = screen.getByTestId(DATA_TEST_ID.PROFILE_CONTENT);
      expect(contentContainer).toBeInTheDocument();

      // AND ProfileCard is called with null values
      expect(ProfileCard).toHaveBeenCalledWith(
        {
          name: null,
          location: null,
          school: null,
          program: null,
          year: null,
          isLoading: false,
        },
        expect.anything()
      );

      // AND SecurityCard is called with null email
      expect(SecurityCard).toHaveBeenCalledWith(
        {
          email: null,
          isLoading: false,
        },
        expect.anything()
      );

      // AND PreferencesCard is called with null values
      expect(PreferencesCard).toHaveBeenCalledWith(
        {
          language: null,
          acceptedTcDate: null,
          isLoading: false,
        },
        expect.anything()
      );

      // AND the content should match the snapshot
      expect(contentContainer).toMatchSnapshot();
    });

    test("should render correctly with partial data", () => {
      // GIVEN profile data with some fields populated
      const givenProps = getDefaultProps({
        name: "John Doe",
        email: "john@example.com",
        // Other fields remain null
      });

      // WHEN the Profile component is rendered
      render(<Profile {...givenProps} />);

      // THEN the component renders successfully
      const contentContainer = screen.getByTestId(DATA_TEST_ID.PROFILE_CONTENT);
      expect(contentContainer).toBeInTheDocument();

      // AND ProfileCard is called with partial data
      expect(ProfileCard).toHaveBeenCalledWith(
        {
          name: "John Doe",
          location: null,
          school: null,
          program: null,
          year: null,
          isLoading: false,
        },
        expect.anything()
      );

      // AND SecurityCard is called with email
      expect(SecurityCard).toHaveBeenCalledWith(
        {
          email: "john@example.com",
          isLoading: false,
        },
        expect.anything()
      );

      // AND the content should match the snapshot
      expect(contentContainer).toMatchSnapshot();
    });
  });

  describe("Disabled modules", () => {
    test("should show the cards of the career modules when they are enabled", () => {
      // GIVEN no module is disabled
      // WHEN the Profile component is rendered
      render(<Profile {...getDefaultProps()} />);

      // THEN the career readiness banner and the career explorer card are shown
      expect(screen.getByTestId("career-readiness-progress-banner")).toBeInTheDocument();
      expect(screen.getByTestId(CAREER_EXPLORER_CARD_DATA_TEST_ID.CARD)).toBeInTheDocument();
    });

    test("should not show the pathways card when knowledge_hub is disabled", () => {
      // GIVEN the knowledge hub, which the card shows and links to, is disabled
      (getDisabledModules as jest.Mock).mockReturnValue(["knowledge_hub"]);

      // WHEN the Profile component is rendered
      render(<Profile {...getDefaultProps()} />);

      // THEN the pathways card is not shown
      expect(screen.queryByTestId(CAREER_EXPLORER_CARD_DATA_TEST_ID.CARD)).not.toBeInTheDocument();
    });

    test("should keep the pathways card when only career_explorer is disabled", () => {
      // GIVEN only the career explorer is disabled
      (getDisabledModules as jest.Mock).mockReturnValue(["career_explorer"]);

      // WHEN the Profile component is rendered
      render(<Profile {...getDefaultProps()} />);

      // THEN the pathways card is still shown, since its links go to the knowledge hub
      expect(screen.getByTestId(CAREER_EXPLORER_CARD_DATA_TEST_ID.CARD)).toBeInTheDocument();
    });

    test("should leave the disabled modules out of the profile strength breakdown", () => {
      // GIVEN career readiness and career explorer are disabled
      (getDisabledModules as jest.Mock).mockReturnValue(["job_readiness", "career_explorer"]);

      // WHEN the Profile component is rendered
      render(<Profile {...getDefaultProps()} />);

      // THEN the breakdown shows the 3 components of the conversation only (0 is the overall bar)
      expect(screen.getByTestId(MODULE_PROGRESS_CARD_DATA_TEST_ID.MODULE_PROGRESS(3))).toBeInTheDocument();
      expect(screen.queryByTestId(MODULE_PROGRESS_CARD_DATA_TEST_ID.MODULE_PROGRESS(4))).not.toBeInTheDocument();
    });

    test("should not show the profile strength when no enabled module has a component", () => {
      // GIVEN every module with a profile strength component is disabled
      (getDisabledModules as jest.Mock).mockReturnValue(["skills_discovery", "job_readiness", "career_explorer"]);

      // WHEN the Profile component is rendered
      render(<Profile {...getDefaultProps()} />);

      // THEN the profile strength card is not shown
      expect(screen.queryByTestId(MODULE_PROGRESS_CARD_DATA_TEST_ID.MODULE_PROGRESS_CARD)).not.toBeInTheDocument();
    });

    test("should not show the career readiness banner when job_readiness is disabled", () => {
      // GIVEN the career readiness module is disabled
      (getDisabledModules as jest.Mock).mockReturnValue(["job_readiness"]);

      // WHEN the Profile component is rendered
      render(<Profile {...getDefaultProps()} />);

      // THEN the career readiness banner is not shown
      expect(screen.queryByTestId("career-readiness-progress-banner")).not.toBeInTheDocument();
    });
  });
});

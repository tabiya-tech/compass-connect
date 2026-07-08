import "src/_test_utilities/consoleMock";
import "src/_test_utilities/envServiceMock";

import { renderHook, waitFor } from "src/_test_utilities/test-utils";
import { useUserProfile } from "./useUserProfile";
import UserMeService from "src/userMe/UserMeService";
import ChatService from "src/chat/ChatService/ChatService";
import type { ModuleSummary } from "src/careerReadiness/types";
import { ConversationPhase } from "src/chat/chatProgressbar/types";

// Mock all external dependencies
jest.mock("src/userMe/UserMeService");
jest.mock("src/chat/ChatService/ChatService");
jest.mock("src/auth/services/AuthenticationState.service", () => ({
  __esModule: true,
  default: { getInstance: jest.fn(() => ({ getUser: jest.fn(() => ({ id: "user-1", email: "test@test.com" })) })) },
}));
jest.mock("src/userPreferences/UserPreferencesStateService", () => ({
  __esModule: true,
  default: {
    getInstance: jest.fn(() => ({
      getUserPreferences: jest.fn(() => ({ accepted_tc: null, language: "en" })),
      getActiveSessionId: jest.fn(() => 123),
    })),
  },
}));
jest.mock("./utils/fetchSkills", () => ({
  fetchSkills: jest.fn(() =>
    Promise.resolve({
      workSkills: [],
      educationSkills: [],
      totalExperiences: 3,
      exploredExperiences: 1,
      experiences: [{ UUID: "exp-1" }, { UUID: "exp-2" }, { UUID: "exp-3" }],
    })
  ),
}));

const mockModules: ModuleSummary[] = [
  {
    id: "m1",
    title: "Module 1",
    description: "",
    icon: "",
    status: "COMPLETED",
    sort_order: 1,
    input_placeholder: "",
    active_conversation_id: null,
    topics: [],
  },
  {
    id: "m2",
    title: "Module 2",
    description: "",
    icon: "",
    status: "IN_PROGRESS",
    sort_order: 2,
    input_placeholder: "",
    active_conversation_id: "conv-123",
    topics: [],
  },
];

const mockProfileResponse = {
  personal_data: null,
  programme_skills: [],
};

const mockConversationPhase = {
  percentage: 33,
  phase: ConversationPhase.COLLECT_EXPERIENCES,
  current: 2,
  total: 2,
};

const mockChatHistoryResponse = {
  messages: [],
  conversation_completed: false,
  conversation_conducted_at: null,
  experiences_explored: 0,
  current_phase: mockConversationPhase,
};

const mockProgressResponse = {
  skills_interests_progress: 0,
  career_readiness_modules: mockModules,
  sector_engagement: [],
};

describe("useUserProfile", () => {
  let mockGetProfile: jest.Mock;
  let mockGetProgress: jest.Mock;
  let mockGetChatHistory: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetProfile = jest.fn(() => Promise.resolve(mockProfileResponse));
    mockGetProgress = jest.fn(() => Promise.resolve(mockProgressResponse));
    mockGetChatHistory = jest.fn(() => Promise.resolve(mockChatHistoryResponse));

    (UserMeService.getInstance as jest.Mock).mockReturnValue({
      getProfile: mockGetProfile,
      getProgress: mockGetProgress,
    });
    (ChatService.getInstance as jest.Mock).mockReturnValue({
      getChatHistory: mockGetChatHistory,
    });
  });

  test("should fetch and return module statuses from UserMeService.getProgress", async () => {
    // WHEN the hook is rendered
    const { result } = renderHook(() => useUserProfile());

    // THEN eventually modules are populated from the API
    await waitFor(() => {
      expect(result.current.isLoadingModules).toBe(false);
    });

    expect(result.current.profileData.modules).toEqual(mockModules);
  });

  test("should populate the conversation phase from the chat history", async () => {
    // WHEN the hook is rendered
    const { result } = renderHook(() => useUserProfile());

    // THEN eventually the conversation phase is populated from the chat history of the active session
    await waitFor(() => {
      expect(result.current.isLoadingModules).toBe(false);
    });

    expect(mockGetChatHistory).toHaveBeenCalledWith(123);
    expect(result.current.profileData.conversationPhase).toEqual(mockConversationPhase);
  });

  test("should leave the conversation phase null when the chat history fetch fails", async () => {
    // GIVEN the chat history fetch fails
    mockGetChatHistory.mockRejectedValue(new Error("Network error"));

    // WHEN the hook is rendered
    const { result } = renderHook(() => useUserProfile());

    // THEN the rest of the progress data still loads and the phase stays null
    await waitFor(() => {
      expect(result.current.isLoadingModules).toBe(false);
    });

    expect(result.current.profileData.conversationPhase).toBeNull();
    expect(result.current.profileData.modules).toEqual(mockModules);
    expect(result.current.errors.modules).toBeNull();
  });

  test("should populate experiences from fetchSkills", async () => {
    // WHEN the hook is rendered
    const { result } = renderHook(() => useUserProfile());

    // THEN eventually the experiences are populated from fetchSkills
    await waitFor(() => {
      expect(result.current.isLoadingSkills).toBe(false);
    });

    expect(result.current.profileData.totalExperiences).toBe(3);
    expect(result.current.profileData.exploredExperiences).toBe(1);
    expect(result.current.profileData.experiences).toHaveLength(3);
  });

  test("should set modules error when progress API call fails", async () => {
    // GIVEN the service throws
    (UserMeService.getInstance as jest.Mock).mockReturnValue({
      getProfile: jest.fn(() => Promise.resolve(mockProfileResponse)),
      getProgress: jest.fn(() => Promise.reject(new Error("Network error"))),
    });

    // WHEN the hook is rendered
    const { result } = renderHook(() => useUserProfile());

    // THEN modules error is set and modules remain empty
    await waitFor(() => {
      expect(result.current.isLoadingModules).toBe(false);
    });

    expect(result.current.errors.modules).toBeInstanceOf(Error);
    expect(result.current.profileData.modules).toEqual([]);
  });

  test("should populate personal data from UserMeService.getProfile", async () => {
    // GIVEN the profile endpoint returns data
    (UserMeService.getInstance as jest.Mock).mockReturnValue({
      getProfile: jest.fn(() =>
        Promise.resolve({
          personal_data: {
            first_name: "Bupe",
            last_name: "Phiri",
            province: "Lusaka",
            institution_name: "UNZA",
            programme_name: "ICT",
            school_year: "Year 2",
          },
          programme_skills: ["JavaScript", "Python"],
        })
      ),
      getProgress: jest.fn(() => Promise.resolve(mockProgressResponse)),
    });

    const { result } = renderHook(() => useUserProfile());

    await waitFor(() => {
      expect(result.current.isLoadingProfile).toBe(false);
    });

    expect(result.current.profileData.name).toBe("Bupe Phiri");
    expect(result.current.profileData.location).toBe("Lusaka");
    expect(result.current.profileData.school).toBe("UNZA");
    expect(result.current.profileData.programmeSkills).toEqual(["JavaScript", "Python"]);
  });
});

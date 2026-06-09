import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { Box } from "@mui/material";
import CareerReadinessChat from "src/careerReadiness/components/CareerReadinessChat/CareerReadinessChat";
import CareerReadinessService from "src/careerReadiness/services/CareerReadinessService";
import type { CareerReadinessConversationResponse } from "src/careerReadiness/types";

const meta: Meta<typeof CareerReadinessChat> = {
  title: "CareerReadiness/CareerReadinessChat",
  component: CareerReadinessChat,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <Box sx={{ height: "100vh", display: "flex", flexDirection: "column" }}>
        <Story />
      </Box>
    ),
    (Story, context) => {
      const storyName = context.name ?? "";
      const mockService = CareerReadinessService.getInstance();

      const getTimestamp = (minutesAgo: number) => new Date(Date.now() - minutesAgo * 60 * 1000).toISOString();

      const mockHistory: CareerReadinessConversationResponse = {
        conversation_id: "conv-1",
        module_id: "professional-identity",
        module_completed: false,
        messages: [
          {
            message_id: "m1",
            message:
              "Welcome! In this module we'll explore your professional identity and skills. How would you describe yourself in a work context?",
            sent_at: getTimestamp(5),
            sender: "AGENT",
          },
          {
            message_id: "m2",
            message: "I'm not sure where to start.",
            sent_at: getTimestamp(4),
            sender: "USER",
          },
          {
            message_id: "m3",
            message:
              "That's okay. Think about your past roles, volunteer work, or studies. What skills did you use? Start with one example.",
            sent_at: getTimestamp(3),
            sender: "AGENT",
          },
        ],
      };

      (mockService as any).createConversation = async (moduleId: string) => ({
        conversation_id: "conv-new",
        module_id: moduleId,
        module_completed: false,
        messages: [
          {
            message_id: "w1",
            message: "Let's get started. What would you like to work on first?",
            sent_at: getTimestamp(0),
            sender: "AGENT",
          },
        ],
      });

      (mockService as any).getConversationHistory = async (_moduleId: string, _conversationId: string) => {
        if (storyName.includes("Loading")) {
          await new Promise((r) => setTimeout(r, 2000));
        }
        return mockHistory;
      };

      (mockService as any).sendMessage = async (_moduleId: string, _conversationId: string, userInput: string) => ({
        ...mockHistory,
        messages: [
          ...mockHistory.messages,
          {
            message_id: "u-new",
            message: userInput,
            sent_at: getTimestamp(0),
            sender: "USER",
          },
          {
            message_id: "a-new",
            message: "Thanks for sharing. Can you tell me more about how you used that skill?",
            sent_at: getTimestamp(0),
            sender: "AGENT",
          },
        ],
      });

      return <Story />;
    },
  ],
};

export default meta;

type Story = StoryObj<typeof CareerReadinessChat>;

const defaultArgs = {
  moduleId: "professional-identity",
  moduleTitle: "Professional Identity & Skills Mapping",
  inputPlaceholder: "Ask about professional identity and skills…",
};

export const WithConversation: Story = {
  args: {
    ...defaultArgs,
    initialConversationId: "conv-1",
  },
};

export const LoadingHistory: Story = {
  args: {
    ...defaultArgs,
    initialConversationId: "conv-1",
  },
};

const completedHistory: CareerReadinessConversationResponse = {
  conversation_id: "conv-completed",
  module_id: "professional-identity",
  module_completed: true,
  quiz_passed: true,
  conversation_mode: "SUPPORT",
  covered_topics: ["Professional identity", "Transferable skills"],
  messages: [
    {
      message_id: "m1",
      message:
        "Welcome! In this module we'll explore your professional identity and skills. How would you describe yourself in a work context?",
      sent_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
      sender: "AGENT",
    },
    {
      message_id: "m2",
      message: "I have experience in teamwork and problem-solving.",
      sent_at: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
      sender: "USER",
    },
    {
      message_id: "m3",
      message:
        "Well done! You've passed the quiz for this module. You can continue to ask me follow-up questions here.",
      sent_at: new Date(Date.now() - 1 * 60 * 1000).toISOString(),
      sender: "AGENT",
    },
  ],
};

/** Simulates backend having just delivered the quiz (quiz_available true); chat will fetch quiz and show quiz UI. */
const historyWithQuizAvailable: CareerReadinessConversationResponse = {
  conversation_id: "conv-quiz-delivered",
  module_id: "professional-identity",
  module_completed: false,
  quiz_available: true,
  messages: [
    {
      message_id: "m1",
      message:
        "Welcome! In this module we'll explore your professional identity and skills. How would you describe yourself in a work context?",
      sent_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
      sender: "AGENT",
    },
    {
      message_id: "m2",
      message: "I have experience in teamwork and problem-solving.",
      sent_at: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
      sender: "USER",
    },
    {
      message_id: "m3",
      message: "Great work! You've covered the key topics. It's time for a short quiz to check your understanding.",
      sent_at: new Date(Date.now() - 1 * 60 * 1000).toISOString(),
      sender: "AGENT",
    },
  ],
};

const mockQuizQuestions = [
  {
    question: "What best describes your professional identity?",
    options: [
      "A. Your job title alone",
      "B. Your unique combination of values, skills, experiences, and aspirations",
      "C. The company you work for",
      "D. Your salary and benefits",
    ],
  },
  {
    question: "Which of the following is a technical skill?",
    options: ["A. Teamwork", "B. Leadership", "C. Data analysis", "D. Time management"],
  },
];

export const QuizDelivered: Story = {
  args: {
    ...defaultArgs,
    initialConversationId: "conv-quiz-delivered",
  },
  decorators: [
    (Story) => {
      const mockService = CareerReadinessService.getInstance() as any;
      mockService.getConversationHistory = async () => historyWithQuizAvailable;
      mockService.getQuiz = async () => ({ questions: mockQuizQuestions });
      mockService.sendMessage = async () => historyWithQuizAvailable;
      mockService.submitQuiz = async () => ({
        score: 2,
        total: 2,
        passed: true,
        question_results: [
          { question_index: 1, is_correct: true },
          { question_index: 2, is_correct: true },
        ],
        module_completed: true,
        conversation_mode: "SUPPORT",
      });
      return <Story />;
    },
  ],
};

export const ModuleCompleted: Story = {
  args: {
    ...defaultArgs,
    initialConversationId: "conv-completed",
  },
  decorators: [
    (Story) => {
      const mockService = CareerReadinessService.getInstance() as any;
      mockService.getConversationHistory = async () => completedHistory;
      mockService.sendMessage = async () => completedHistory;
      return <Story />;
    },
  ],
};

/** Quiz is shown; submit returns failed so user sees "Your answers" + feedback and quiz with result card + Retry. */
export const QuizFailedThenRetry: Story = {
  args: {
    ...defaultArgs,
    initialConversationId: "conv-quiz-delivered",
  },
  decorators: [
    (Story) => {
      const mockService = CareerReadinessService.getInstance() as any;
      mockService.getConversationHistory = async () => historyWithQuizAvailable;
      mockService.getQuiz = async () => ({ questions: mockQuizQuestions });
      mockService.sendMessage = async () => historyWithQuizAvailable;
      mockService.submitQuiz = async () => ({
        score: 0,
        total: 2,
        passed: false,
        question_results: [
          { question_index: 1, is_correct: false },
          { question_index: 2, is_correct: false },
        ],
        module_completed: false,
      });
      return <Story />;
    },
  ],
};

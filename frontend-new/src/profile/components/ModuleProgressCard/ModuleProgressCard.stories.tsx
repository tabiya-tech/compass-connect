import type { Meta, StoryObj } from "@storybook/react";
import { ModuleProgressCard } from "./ModuleProgressCard";
import type { ProfileStrengthBreakdown } from "src/profile/utils/calculateProfileStrength";

const getBreakdown = (
  experienceCollection: number,
  skillsDiscovery: number,
  preferences: number,
  careerReadiness: number,
  careerExplorer: number
): ProfileStrengthBreakdown => ({
  experienceCollection: { points: experienceCollection, max: 20 },
  skillsDiscovery: { points: skillsDiscovery, max: 25 },
  preferences: { points: preferences, max: 20 },
  careerReadiness: { points: careerReadiness, max: 30 },
  careerExplorer: { points: careerExplorer, max: 5 },
  overall: Math.round(experienceCollection + skillsDiscovery + preferences + careerReadiness + careerExplorer),
});

const meta: Meta<typeof ModuleProgressCard> = {
  title: "Profile/Components/ModuleProgressCard",
  component: ModuleProgressCard,
  tags: ["autodocs"],
};

export default meta;

type Story = StoryObj<typeof ModuleProgressCard>;

export const Default: Story = {
  args: {
    profileStrength: getBreakdown(15, 12.5, 0, 10, 5),
  },
};

export const NotStarted: Story = {
  args: {
    profileStrength: getBreakdown(0, 0, 0, 0, 0),
  },
};

export const MidJourney: Story = {
  args: {
    profileStrength: getBreakdown(10, 8.33, 0, 5, 0),
  },
};

export const ConversationFinished: Story = {
  args: {
    profileStrength: getBreakdown(20, 25, 20, 0, 0),
  },
};

export const FullyComplete: Story = {
  args: {
    profileStrength: getBreakdown(20, 25, 20, 30, 5),
  },
};

export const Loading: Story = {
  args: {
    profileStrength: getBreakdown(0, 0, 0, 0, 0),
    isLoading: true,
  },
};

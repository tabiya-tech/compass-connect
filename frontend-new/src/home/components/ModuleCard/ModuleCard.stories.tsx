import type { Meta, StoryObj } from "@storybook/react";
import ModuleCard from "src/home/components/ModuleCard/ModuleCard";
import { PlatformModuleConfig, PlatformModule } from "src/home/modulesService";

const meta: Meta<typeof ModuleCard> = {
  title: "Home/ModuleCard",
  component: ModuleCard,
  tags: ["autodocs"],
  argTypes: {
    badgeStatus: {
      control: "select",
      options: [null, "continue", "completed"],
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 320, height: 200 }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ModuleCard>;

// Mock module data using real translation keys
const mockModule: PlatformModuleConfig = {
  id: PlatformModule.SKILLS_DISCOVERY,
  labelKey: "home.modules.skillsDiscovery",
  descriptionKey: "home.modules.skillsDiscoveryDesc",
  route: "/skills-interests",
};

export const Default: Story = {
  args: {
    module: mockModule,
    badgeStatus: null,
  },
};

export const WithContinueBadge: Story = {
  args: {
    module: mockModule,
    badgeStatus: "continue",
  },
};

export const WithCompletedBadge: Story = {
  args: {
    module: mockModule,
    badgeStatus: "completed",
  },
};

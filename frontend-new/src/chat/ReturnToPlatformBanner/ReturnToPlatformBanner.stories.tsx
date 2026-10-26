import type { Meta, StoryObj } from "@storybook/react";
import ReturnToPlatformBanner from "./ReturnToPlatformBanner";

const meta: Meta<typeof ReturnToPlatformBanner> = {
  title: "Chat/ReturnToPlatformBanner",
  component: ReturnToPlatformBanner,
  tags: ["autodocs"],
};

export default meta;

type Story = StoryObj<typeof ReturnToPlatformBanner>;

export const Shown: Story = {
  args: {
    returnUrl: "https://partner.example.org/perfil",
  },
};

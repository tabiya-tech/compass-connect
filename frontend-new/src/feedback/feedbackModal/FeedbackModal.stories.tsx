import type { Meta, StoryObj } from "@storybook/react";
import FeedbackModal from "src/feedback/feedbackModal/FeedbackModal";

const meta: Meta<typeof FeedbackModal> = {
  title: "Components/FeedbackModal",
  component: FeedbackModal,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof FeedbackModal>;

export const Open: Story = {
  args: {
    isOpen: true,
    onClose: () => {},
    onSubmit: () => {},
  },
};

export const Closed: Story = {
  args: {
    isOpen: false,
    onClose: () => {},
    onSubmit: () => {},
  },
};

// Tiny 1x1 transparent PNG used purely so the preview thumbnail has something to render.
const STORYBOOK_PIXEL_PNG =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

export const WithScreenshot: Story = {
  args: {
    isOpen: true,
    onClose: () => {},
    onSubmit: () => {},
    screenshotDataUrl: STORYBOOK_PIXEL_PNG,
    screenshotBytes: new Uint8Array([1, 2, 3]),
    onRemoveScreenshot: () => {},
  },
};

export const CapturingScreenshot: Story = {
  args: {
    isOpen: true,
    onClose: () => {},
    onSubmit: () => {},
    isCapturingScreenshot: true,
  },
};

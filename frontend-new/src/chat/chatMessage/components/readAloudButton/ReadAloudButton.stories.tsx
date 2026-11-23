import type { Meta, StoryObj } from "@storybook/react";
import ReadAloudButton from "src/chat/chatMessage/components/readAloudButton/ReadAloudButton";
import { ReadAloudContext } from "src/textToSpeech/ReadAloudContext";
import { PlaybackState } from "src/textToSpeech/textToSpeech.types";

const givenMessageId = "message-1";

const withPlayerState = (state: PlaybackState) => (Story: () => JSX.Element) => (
  <ReadAloudContext.Provider value={{ state, play: () => {}, stop: () => {} }}>
    <Story />
  </ReadAloudContext.Provider>
);

const meta: Meta<typeof ReadAloudButton> = {
  title: "Chat/ChatMessage/ReadAloudButton",
  component: ReadAloudButton,
  tags: ["autodocs"],
  args: {
    messageId: givenMessageId,
    message: "Tell me about your last job, and what you did there.",
  },
};

export default meta;

type Story = StoryObj<typeof ReadAloudButton>;

export const Idle: Story = {
  decorators: [withPlayerState({ status: "idle" })],
};

export const Loading: Story = {
  decorators: [withPlayerState({ status: "loading", messageId: givenMessageId })],
};

export const Playing: Story = {
  decorators: [withPlayerState({ status: "playing", messageId: givenMessageId })],
};

export const AnotherMessageIsPlaying: Story = {
  decorators: [withPlayerState({ status: "playing", messageId: "another-message" })],
};

export const AfterAnError: Story = {
  decorators: [withPlayerState({ status: "error", messageId: givenMessageId, error: "unavailable" })],
};

import React, { ReactElement } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import ChatList from "./ChatList";
import { ConversationMessageSender } from "src/chat/ChatService/ChatService.types";
import { IChatMessage } from "src/chat/Chat.types";
import { nanoid } from "nanoid";
import AgentChatMessage, {
  AgentChatMessageProps,
  AGENT_CHAT_MESSAGE_TYPE,
} from "src/chat/chatMessage/agentChatMessage/AgentChatMessage";
import UserChatMessage, {
  UserChatMessageProps,
  USER_CHAT_MESSAGE_TYPE,
} from "src/chat/chatMessage/userChatMessage/UserChatMessage";
import TypingChatMessage, {
  TypingChatMessageProps,
  TYPING_CHAT_MESSAGE_TYPE,
} from "src/chat/chatMessage/typingChatMessage/TypingChatMessage";
import ConversationConclusionChatMessage, {
  ConversationConclusionChatMessageProps,
  CONVERSATION_CONCLUSION_CHAT_MESSAGE_TYPE,
} from "src/chat/chatMessage/conversationConclusionChatMessage/ConversationConclusionChatMessage";
import ErrorChatMessage, {
  ERROR_CHAT_MESSAGE_TYPE,
  ErrorChatMessageProps,
} from "src/chat/chatMessage/errorChatMessage/ErrorChatMessage";
import UserPreferencesStateService from "src/userPreferences/UserPreferencesStateService";
import { EnvVariables } from "src/envService";
import { SupportedLocales } from "src/i18n/constants";
import TextToSpeechService from "src/textToSpeech/TextToSpeechService";

// Helper function to create a message with its component
const createMessage = (
  message: string,
  sender: ConversationMessageSender,
  type: string = USER_CHAT_MESSAGE_TYPE,
  reaction: any = null
): IChatMessage<any> => {
  const messageData = {
    message_id: nanoid(),
    sender,
    message,
    sent_at: new Date().toISOString(),
    type,
    reaction,
  };

  let component: (props: any) => ReactElement<any>;
  if (type === TYPING_CHAT_MESSAGE_TYPE) {
    component = (props) => <TypingChatMessage {...(props as TypingChatMessageProps)} />;
  } else if (type === CONVERSATION_CONCLUSION_CHAT_MESSAGE_TYPE) {
    component = (props) => <ConversationConclusionChatMessage {...(props as ConversationConclusionChatMessageProps)} />;
  } else if (type === ERROR_CHAT_MESSAGE_TYPE) {
    component = (props) => <ErrorChatMessage {...(props as ErrorChatMessageProps)} />;
  } else {
    component =
      sender === ConversationMessageSender.USER
        ? (props) => <UserChatMessage {...(props as UserChatMessageProps)} />
        : (props) => <AgentChatMessage {...(props as AgentChatMessageProps)} />;
  }

  return {
    type: messageData.type,
    message_id: messageData.message_id,
    sender: messageData.sender,
    payload: messageData,
    component,
  };
};

const meta: Meta<typeof ChatList> = {
  title: "Chat/ChatList",
  component: ChatList,
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => {
      // Mock UserPreferencesStateService
      const mockService = UserPreferencesStateService.getInstance();
      mockService.getActiveSessionId = () => 1234;
      mockService.activeSessionHasCustomerSatisfactionRating = () => false;
      mockService.activeSessionHasOverallFeedback = () => false;
      return <Story />;
    },
  ],
};

export default meta;
type Story = StoryObj<typeof ChatList>;

export const Shown: Story = {
  args: {
    messages: [
      createMessage("Hello, how can I help you?", ConversationMessageSender.COMPASS, AGENT_CHAT_MESSAGE_TYPE),
      createMessage("I need help with something", ConversationMessageSender.USER, USER_CHAT_MESSAGE_TYPE),
    ],
  },
};

export const Empty: Story = {
  args: {
    messages: [],
  },
};

export const Typing: Story = {
  args: {
    messages: [
      createMessage("Hello, how can I help you?", ConversationMessageSender.USER, USER_CHAT_MESSAGE_TYPE),
      createMessage("", ConversationMessageSender.COMPASS, TYPING_CHAT_MESSAGE_TYPE),
    ],
  },
};

export const TypingWhenEmpty: Story = {
  args: {
    messages: [createMessage("", ConversationMessageSender.COMPASS, TYPING_CHAT_MESSAGE_TYPE)],
  },
};

export const SingleMessage: Story = {
  args: {
    messages: [createMessage("Hello, I'm Compass", ConversationMessageSender.COMPASS, AGENT_CHAT_MESSAGE_TYPE)],
  },
};

export const MultipleMessages: Story = {
  args: {
    messages: [
      createMessage("Hello", ConversationMessageSender.USER, USER_CHAT_MESSAGE_TYPE),
      createMessage("Hi, I'm Compass", ConversationMessageSender.COMPASS, AGENT_CHAT_MESSAGE_TYPE),
      createMessage(
        "Thank you for using compass",
        ConversationMessageSender.COMPASS,
        CONVERSATION_CONCLUSION_CHAT_MESSAGE_TYPE
      ),
      createMessage("Typing...", ConversationMessageSender.COMPASS, TYPING_CHAT_MESSAGE_TYPE),
    ],
  },
};

export const LongConversation: Story = {
  args: {
    messages: Array.from({ length: 100 }, (_, i) =>
      createMessage(
        `Message ${i}`,
        i % 2 === 0 ? ConversationMessageSender.COMPASS : ConversationMessageSender.USER,
        i % 2 === 0 ? AGENT_CHAT_MESSAGE_TYPE : USER_CHAT_MESSAGE_TYPE
      )
    ),
  },
};

/**
 * Read aloud on, in every locale: each AI message has the read aloud button beside it, also when two messages
 * from Compass follow each other. The audio is a short silence, so the button goes through loading and playing.
 */
export const WithReadAloud: Story = {
  args: {
    messages: [
      createMessage("Hi, I'm Compass.", ConversationMessageSender.COMPASS, AGENT_CHAT_MESSAGE_TYPE),
      createMessage(
        "Let's start with your **work experience**. Tell me about:\n- the jobs you have had\n- the work you did for your family or community",
        ConversationMessageSender.COMPASS,
        AGENT_CHAT_MESSAGE_TYPE
      ),
      createMessage("I worked as a carpenter for three years", ConversationMessageSender.USER, USER_CHAT_MESSAGE_TYPE),
    ],
  },
  decorators: [
    (Story) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).tabiyaConfig = {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ...(window as any).tabiyaConfig,
        [EnvVariables.FRONTEND_SPEECH_CONFIG]: window.btoa(
          JSON.stringify({ textToSpeech: { enabled: true, locales: SupportedLocales } })
        ),
      };
      TextToSpeechService.getInstance().synthesize = async () => {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        // 2 seconds of silence, as a WAV file
        const sampleRate = 8000;
        const samples = sampleRate * 2;
        const buffer = new ArrayBuffer(44 + samples);
        const view = new DataView(buffer);
        const writeText = (offset: number, text: string) =>
          text.split("").forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
        writeText(0, "RIFF");
        view.setUint32(4, 36 + samples, true);
        writeText(8, "WAVEfmt ");
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 1, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, sampleRate, true);
        view.setUint16(32, 1, true);
        view.setUint16(34, 8, true);
        writeText(36, "data");
        view.setUint32(40, samples, true);
        new Uint8Array(buffer, 44).fill(128);
        return new Blob([buffer], { type: "audio/wav" });
      };
      return <Story />;
    },
  ],
};

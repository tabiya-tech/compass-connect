// mute the console
import "src/_test_utilities/consoleMock";

import React from "react";
import { render, screen, fireEvent } from "src/_test_utilities/test-utils";
import { ChatProvider } from "src/chat/ChatContext";
import ChatView, { DATA_TEST_ID } from "./ChatView";
import { DATA_TEST_ID as CHAT_LIST_DATA_TEST_ID } from "src/chat/chatList/ChatList";
import { DATA_TEST_ID as CHAT_MESSAGE_FIELD_DATA_TEST_ID } from "src/chat/ChatMessageField/ChatMessageField";
import { DATA_TEST_ID as QUICK_REPLY_BUTTONS_DATA_TEST_ID } from "src/chat/chatMessage/suggestedActions/QuickReplyButtons";
import { ConversationMessageSender, QuickReplyOption } from "src/chat/ChatService/ChatService.types";
import { IChatMessage } from "src/chat/Chat.types";
import { nanoid } from "nanoid";
import { USER_CHAT_MESSAGE_TYPE } from "src/chat/chatMessage/userChatMessage/UserChatMessage";
import { AGENT_CHAT_MESSAGE_TYPE } from "src/chat/chatMessage/agentChatMessage/AgentChatMessage";
import UserChatMessage, { UserChatMessageProps } from "src/chat/chatMessage/userChatMessage/UserChatMessage";
import AgentChatMessage, { AgentChatMessageProps } from "src/chat/chatMessage/agentChatMessage/AgentChatMessage";

// Mock the ChatList component
jest.mock("src/chat/chatList/ChatList", () => {
  const originalModule = jest.requireActual("src/chat/chatList/ChatList");
  return {
    __esModule: true,
    ...originalModule,
    default: jest.fn(({ messages }) => (
      <div data-testid={originalModule.DATA_TEST_ID.CHAT_LIST_CONTAINER}>{messages.length} messages</div>
    )),
  };
});

// Mock the ChatMessageField component
jest.mock("src/chat/ChatMessageField/ChatMessageField", () => {
  const originalModule = jest.requireActual("src/chat/ChatMessageField/ChatMessageField");
  return {
    __esModule: true,
    ...originalModule,
    default: jest.fn(() => <div data-testid={originalModule.DATA_TEST_ID.CHAT_MESSAGE_FIELD_CONTAINER}></div>),
  };
});

// Mock the QuickReplyButtons component
jest.mock("src/chat/chatMessage/suggestedActions/QuickReplyButtons", () => {
  const originalModule = jest.requireActual("src/chat/chatMessage/suggestedActions/QuickReplyButtons");
  return {
    __esModule: true,
    ...originalModule,
    default: jest.fn(({ options, onSelect }) => (
      <div data-testid={originalModule.DATA_TEST_ID.QUICK_REPLY_CONTAINER}>
        {options.map((option: QuickReplyOption, index: number) => (
          <button key={index} data-testid={`quick-reply-${index}`} onClick={() => onSelect(option.label)}>
            {option.label}
          </button>
        ))}
      </div>
    )),
  };
});

jest.mock("src/auth/services/FirebaseAuthenticationService/socialAuth/FirebaseSocialAuthentication.service", () => {
  return {
    __esModule: true,
    default: jest.fn().mockImplementation(() => {
      return {
        logout: jest.fn(),
      };
    }),
  };
});

describe("ChatView", () => {
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  const mockHandleOpenExperiencesDrawer = jest.fn();
  const mockRemoveMessage = jest.fn();
  const mockAddMessage = jest.fn();
  const mockHandleSend = jest.fn();

  const renderChatView = (
    messages: IChatMessage<any>[] = [],
    quickReplyOptions?: QuickReplyOption[] | null,
    onQuickReplyClick?: (label: string) => void,
    children?: React.ReactNode
  ) => {
    return render(
      <ChatProvider
        handleOpenExperiencesDrawer={mockHandleOpenExperiencesDrawer}
        removeMessageFromChat={mockRemoveMessage}
        addMessageToChat={mockAddMessage}
      >
        <ChatView
          messages={messages}
          quickReplyOptions={quickReplyOptions}
          onQuickReplyClick={onQuickReplyClick}
          messageFieldProps={{
            handleSend: mockHandleSend,
            aiIsTyping: false,
            isChatFinished: false,
          }}
        >
          {children}
        </ChatView>
      </ChatProvider>
    );
  };

  test("should render the ChatView container with all main sections", () => {
    // GIVEN no messages
    const givenMessages: IChatMessage<any>[] = [];

    // WHEN the ChatView is rendered
    renderChatView(givenMessages);

    // THEN expect the main container to be visible
    expect(screen.getByTestId(DATA_TEST_ID.CHAT_VIEW_CONTAINER)).toBeInTheDocument();
    // AND expect the messages area to be visible
    expect(screen.getByTestId(DATA_TEST_ID.CHAT_VIEW_MESSAGES_AREA)).toBeInTheDocument();
    // AND expect the input area to be visible
    expect(screen.getByTestId(DATA_TEST_ID.CHAT_VIEW_INPUT_AREA)).toBeInTheDocument();
    // AND expect the ChatList to be rendered
    expect(screen.getByTestId(CHAT_LIST_DATA_TEST_ID.CHAT_LIST_CONTAINER)).toBeInTheDocument();
    // AND expect the ChatMessageField to be rendered
    expect(screen.getByTestId(CHAT_MESSAGE_FIELD_DATA_TEST_ID.CHAT_MESSAGE_FIELD_CONTAINER)).toBeInTheDocument();
  });

  test("should render messages in the ChatList", () => {
    // GIVEN messages to display
    const givenDate = new Date().toISOString();
    const givenMessages: IChatMessage<any>[] = [
      {
        type: USER_CHAT_MESSAGE_TYPE,
        message_id: nanoid(),
        sender: ConversationMessageSender.USER,
        payload: {
          message: "Hello",
          sent_at: givenDate,
          fill_color: "primary",
        } as UserChatMessageProps,
        component: (props) => <UserChatMessage {...(props as UserChatMessageProps)} />,
      },
      {
        type: AGENT_CHAT_MESSAGE_TYPE,
        message_id: nanoid(),
        sender: ConversationMessageSender.COMPASS,
        payload: {
          message_id: nanoid(),
          message: "Hi, I'm Compass",
          sent_at: givenDate,
          reaction: null,
        } as AgentChatMessageProps,
        component: (props) => <AgentChatMessage {...(props as AgentChatMessageProps)} />,
      },
    ];

    // WHEN the ChatView is rendered with messages
    renderChatView(givenMessages);

    // THEN expect the ChatList to show the correct number of messages
    expect(screen.getByText("2 messages")).toBeInTheDocument();
  });

  test("should render QuickReplyButtons when quickReplyOptions are provided", () => {
    // GIVEN quick reply options
    const givenQuickReplyOptions: QuickReplyOption[] = [
      { label: "Option 1" },
      { label: "Option 2" },
      { label: "Option 3" },
    ];
    // AND a handler for quick reply clicks
    const givenOnQuickReplyClick = jest.fn();

    // WHEN the ChatView is rendered with quick reply options
    renderChatView([], givenQuickReplyOptions, givenOnQuickReplyClick);

    // THEN expect the quick replies container to be visible
    expect(screen.getByTestId(DATA_TEST_ID.CHAT_VIEW_QUICK_REPLIES_CONTAINER)).toBeInTheDocument();
    // AND expect the QuickReplyButtons to be rendered
    expect(screen.getByTestId(QUICK_REPLY_BUTTONS_DATA_TEST_ID.QUICK_REPLY_CONTAINER)).toBeInTheDocument();
    // AND expect all options to be visible
    expect(screen.getByText("Option 1")).toBeInTheDocument();
    expect(screen.getByText("Option 2")).toBeInTheDocument();
    expect(screen.getByText("Option 3")).toBeInTheDocument();
  });

  test("should call onQuickReplyClick when a quick reply button is clicked", () => {
    // GIVEN quick reply options
    const givenQuickReplyOptions: QuickReplyOption[] = [{ label: "Option 1" }, { label: "Option 2" }];
    // AND a handler for quick reply clicks
    const givenOnQuickReplyClick = jest.fn();

    // WHEN the ChatView is rendered with quick reply options
    renderChatView([], givenQuickReplyOptions, givenOnQuickReplyClick);

    // AND a quick reply button is clicked
    fireEvent.click(screen.getByTestId("quick-reply-0"));

    // THEN expect the handler to be called with the correct label
    expect(givenOnQuickReplyClick).toHaveBeenCalledWith("Option 1");
  });

  test("should NOT render QuickReplyButtons when quickReplyOptions is null", () => {
    // GIVEN null quick reply options
    const givenQuickReplyOptions = null;

    // WHEN the ChatView is rendered without quick reply options
    renderChatView([], givenQuickReplyOptions);

    // THEN expect the quick replies container NOT to be visible
    expect(screen.queryByTestId(DATA_TEST_ID.CHAT_VIEW_QUICK_REPLIES_CONTAINER)).not.toBeInTheDocument();
  });

  test("should NOT render QuickReplyButtons when quickReplyOptions is an empty array", () => {
    // GIVEN empty quick reply options
    const givenQuickReplyOptions: QuickReplyOption[] = [];
    // AND a handler for quick reply clicks
    const givenOnQuickReplyClick = jest.fn();

    // WHEN the ChatView is rendered with empty quick reply options
    renderChatView([], givenQuickReplyOptions, givenOnQuickReplyClick);

    // THEN expect the quick replies container NOT to be visible
    expect(screen.queryByTestId(DATA_TEST_ID.CHAT_VIEW_QUICK_REPLIES_CONTAINER)).not.toBeInTheDocument();
  });

  test("should NOT render QuickReplyButtons when onQuickReplyClick is not provided", () => {
    // GIVEN quick reply options but no handler
    const givenQuickReplyOptions: QuickReplyOption[] = [{ label: "Option 1" }];

    // WHEN the ChatView is rendered without a quick reply handler
    renderChatView([], givenQuickReplyOptions, undefined);

    // THEN expect the quick replies container NOT to be visible
    expect(screen.queryByTestId(DATA_TEST_ID.CHAT_VIEW_QUICK_REPLIES_CONTAINER)).not.toBeInTheDocument();
  });

  test("should render children between messages area and input area", () => {
    // GIVEN a child component
    const givenChild = <div data-testid="test-child">Test Child Content</div>;

    // WHEN the ChatView is rendered with children
    renderChatView([], null, undefined, givenChild);

    // THEN expect the child to be visible
    expect(screen.getByTestId("test-child")).toBeInTheDocument();
    expect(screen.getByText("Test Child Content")).toBeInTheDocument();
  });

  test("should match snapshot with messages and quick replies", () => {
    // GIVEN messages and quick reply options
    const givenDate = new Date("2024-01-01T12:00:00.000Z").toISOString();
    const givenMessages: IChatMessage<any>[] = [
      {
        type: USER_CHAT_MESSAGE_TYPE,
        message_id: "user-msg-1",
        sender: ConversationMessageSender.USER,
        payload: {
          message: "Hello",
          sent_at: givenDate,
          fill_color: "primary",
        } as UserChatMessageProps,
        component: (props) => <UserChatMessage {...(props as UserChatMessageProps)} />,
      },
    ];
    const givenQuickReplyOptions: QuickReplyOption[] = [{ label: "Yes" }, { label: "No" }];
    const givenOnQuickReplyClick = jest.fn();

    // WHEN the ChatView is rendered
    renderChatView(givenMessages, givenQuickReplyOptions, givenOnQuickReplyClick);

    // THEN expect the component to match the snapshot
    expect(screen.getByTestId(DATA_TEST_ID.CHAT_VIEW_CONTAINER)).toMatchSnapshot();
  });
});

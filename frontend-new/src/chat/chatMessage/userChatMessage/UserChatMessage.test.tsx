// mute the console
import "src/_test_utilities/consoleMock";

import UserChatMessage, { DATA_TEST_ID, USER_CHAT_MESSAGE_TYPE } from "./UserChatMessage";
import ChatBubble, {
  DATA_TEST_ID as CHAT_BUBBLE_DATA_TEST_ID,
} from "src/chat/chatMessage/components/chatBubble/ChatBubble";
import { render, screen } from "src/_test_utilities/test-utils";
import { ConversationMessageSender } from "src/chat/ChatService/ChatService.types";
import { nanoid } from "nanoid";

jest.mock("src/chat/chatMessage/components/chatBubble/ChatBubble", () => {
  const originalModule = jest.requireActual("src/chat/chatMessage/components/chatBubble/ChatBubble");
  return {
    __esModule: true,
    ...originalModule,
    default: jest.fn(() => <div data-testid={originalModule.DATA_TEST_ID.CHAT_MESSAGE_BUBBLE_CONTAINER}></div>),
  };
});

describe("render tests", () => {
  beforeAll(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2020, 3, 1));
  });

  afterAll(() => {
    jest.useRealTimers();
  });

  test("should render the User Chat message with a ChatBubble", () => {
    // GIVEN a user chat message sent at a given time
    const givenDate = new Date(2024, 6, 25).toISOString();
    const givenFillColor = "#FF5733";
    const textColor = "#FFFFFF";
    const messageData = {
      message_id: nanoid(),
      sender: ConversationMessageSender.COMPASS,
      message: "Hello, I'm Compass",
      sent_at: givenDate,
      type: USER_CHAT_MESSAGE_TYPE,
      reaction: null,
      fill_color: givenFillColor,
      text_color: textColor,
    };
    // WHEN the user chat message is rendered
    render(<UserChatMessage {...messageData} />);

    // THEN expect the message container to be visible
    expect(screen.getByTestId(DATA_TEST_ID.CHAT_MESSAGE_CONTAINER)).toBeInTheDocument();
    // AND expect the message bubble to be visible
    expect(screen.getByTestId(CHAT_BUBBLE_DATA_TEST_ID.CHAT_MESSAGE_BUBBLE_CONTAINER)).toBeInTheDocument();

    // AND expect the Chat bubble to have been rendered with the expected message and fillColor
    expect(ChatBubble).toHaveBeenNthCalledWith(
      1,
      {
        message: messageData.message,
        sender: ConversationMessageSender.USER,
        fillColor: givenFillColor,
        textColor,
      },
      {}
    );

    // AND expect the component to match the snapshot
    expect(screen.getByTestId(DATA_TEST_ID.CHAT_MESSAGE_CONTAINER)).toMatchSnapshot();
  });
});

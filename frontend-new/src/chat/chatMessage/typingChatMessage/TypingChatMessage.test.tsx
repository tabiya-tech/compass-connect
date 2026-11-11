// mute the console
import "src/_test_utilities/consoleMock";

import { render, screen, act } from "src/_test_utilities/test-utils";
import TypingChatMessage, {
  DATA_TEST_ID,
  UI_TEXT_KEYS,
  WAIT_BEFORE_STILL_WORKING,
  WAIT_BEFORE_THANKS_FOR_WAITING,
} from "src/chat/chatMessage/typingChatMessage/TypingChatMessage";
import { DATA_TEST_ID as CHAT_BUBBLE_DATA_TEST_ID } from "src/chat/chatMessage/components/chatBubble/ChatBubble";
import i18n from "src/i18n/i18n";

// mock chat bubble component
jest.mock("src/chat/chatMessage/components/chatBubble/ChatBubble", () => {
  const originalModule = jest.requireActual("src/chat/chatMessage/components/chatBubble/ChatBubble");
  return {
    __esModule: true,
    ...originalModule,
    default: jest.fn(({ children }) => (
      <div data-testid={originalModule.DATA_TEST_ID.CHAT_MESSAGE_BUBBLE_CONTAINER}>{children}</div>
    )),
  };
});

// mock framer-motion
jest.mock("framer-motion", () => {
  return {
    AnimatePresence: jest.fn(({ children }) => <>{children}</>),
    motion: {
      div: jest.fn(({ children, ...props }) => <div {...props}>{children}</div>),
    },
  };
});

describe("TypingChatMessage", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test("should render the Typing Chat message correctly when ai is typing", () => {
    // GIVEN a Typing Chat message component
    const givenComponent = <TypingChatMessage />;

    // WHEN the Typing Chat message is rendered
    render(givenComponent);

    // THEN expect the message container to be visible
    const typingChatMessageContainer = screen.getByTestId(DATA_TEST_ID.TYPING_CHAT_MESSAGE_CONTAINER);
    expect(typingChatMessageContainer).toBeInTheDocument();
    // AND expect the message bubble to be visible
    expect(screen.getByTestId(CHAT_BUBBLE_DATA_TEST_ID.CHAT_MESSAGE_BUBBLE_CONTAINER)).toBeInTheDocument();
    // AND expect the typing text to be displayed (translated)
    const displayedText = i18n.t(UI_TEXT_KEYS.TYPING);
    expect(screen.getByText(displayedText)).toBeInTheDocument();
    // AND expect to find the 3 animated dots
    expect(screen.getAllByTestId(DATA_TEST_ID.TYPING_CHAT_MESSAGE_DOT)).toHaveLength(3);
    // AND expect the text to be announced to screen readers
    expect(screen.getByRole("status")).toHaveTextContent(displayedText);
    // AND the component to match the snapshot
    expect(typingChatMessageContainer).toMatchSnapshot();
    // THEN expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should render the Typing Chat message correctly when ai is thinking", () => {
    // GIVEN a Typing Chat message component
    const givenComponent = <TypingChatMessage waitBeforeThinking={0} />;

    // WHEN the Typing Chat message is rendered
    render(givenComponent);

    // THEN expect the message container to be visible
    const typingChatMessageContainer = screen.getByTestId(DATA_TEST_ID.TYPING_CHAT_MESSAGE_CONTAINER);
    expect(typingChatMessageContainer).toBeInTheDocument();
    // AND expect the message bubble to be visible
    expect(screen.getByTestId(CHAT_BUBBLE_DATA_TEST_ID.CHAT_MESSAGE_BUBBLE_CONTAINER)).toBeInTheDocument();

    // WHEN the timers advance to the thinking stage
    act(() => {
      jest.advanceTimersByTime(1);
    });

    // THEN expect the thinking text to be displayed (translated)
    const displayedText = i18n.t(UI_TEXT_KEYS.THINKING);
    expect(screen.getByText(displayedText)).toBeInTheDocument();
    // AND expect to find the 3 animated dots
    expect(screen.getAllByTestId(DATA_TEST_ID.TYPING_CHAT_MESSAGE_DOT)).toHaveLength(3);
    // AND expect the text to be announced to screen readers
    expect(screen.getByRole("status")).toHaveTextContent(displayedText);
    // AND the component to match the snapshot
    expect(typingChatMessageContainer).toMatchSnapshot();
    // THEN expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should change from 'Typing' to 'Thinking' text after waitBeforeThinking period", () => {
    // GIVEN a specific wait time in milliseconds
    const waitTime = 1000;
    const givenComponent = <TypingChatMessage waitBeforeThinking={waitTime} />;

    // WHEN the component is rendered
    render(givenComponent);

    // THEN initially it should display the typing text (translated)
    expect(screen.getByText(i18n.t(UI_TEXT_KEYS.TYPING))).toBeInTheDocument();
    // AND the thinking text should not be displayed (translated)
    expect(screen.queryByText(i18n.t(UI_TEXT_KEYS.THINKING))).not.toBeInTheDocument();

    // WHEN advancing time past the waitBeforeThinking time
    act(() => {
      jest.advanceTimersByTime(waitTime + 100);
    });

    // THEN it should now display the thinking text (translated)
    expect(screen.getByText(i18n.t(UI_TEXT_KEYS.THINKING))).toBeInTheDocument();
    // AND the typing text should not be displayed (translated)
    expect(screen.queryByText(i18n.t(UI_TEXT_KEYS.TYPING))).not.toBeInTheDocument();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should move through the stages from 'Typing' to 'Thanks for waiting' on long waits", () => {
    // GIVEN a specific wait time before thinking
    const givenWaitBeforeThinking = 1000;
    render(<TypingChatMessage waitBeforeThinking={givenWaitBeforeThinking} />);

    // THEN initially it should display the typing text
    expect(screen.getByText(i18n.t(UI_TEXT_KEYS.TYPING))).toBeInTheDocument();

    // WHEN the thinking stage is reached
    act(() => {
      jest.advanceTimersByTime(givenWaitBeforeThinking);
    });
    // THEN the thinking text is displayed
    expect(screen.getByText(i18n.t(UI_TEXT_KEYS.THINKING))).toBeInTheDocument();

    // WHEN the still-working stage is reached
    act(() => {
      jest.advanceTimersByTime(WAIT_BEFORE_STILL_WORKING);
    });
    // THEN the still-working text is displayed
    expect(screen.getByText(i18n.t(UI_TEXT_KEYS.STILL_WORKING))).toBeInTheDocument();
    expect(screen.queryByText(i18n.t(UI_TEXT_KEYS.THINKING))).not.toBeInTheDocument();

    // WHEN the thanks-for-waiting stage is reached
    act(() => {
      jest.advanceTimersByTime(WAIT_BEFORE_THANKS_FOR_WAITING - WAIT_BEFORE_STILL_WORKING);
    });
    // THEN the thanks-for-waiting text is displayed
    expect(screen.getByText(i18n.t(UI_TEXT_KEYS.THANKS_FOR_WAITING))).toBeInTheDocument();
    expect(screen.queryByText(i18n.t(UI_TEXT_KEYS.STILL_WORKING))).not.toBeInTheDocument();

    // WHEN more time passes
    act(() => {
      jest.runAllTimers();
    });
    // THEN it stays on the last stage
    expect(screen.getByText(i18n.t(UI_TEXT_KEYS.THANKS_FOR_WAITING))).toBeInTheDocument();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should show the given thinking message in the thinking stage", () => {
    // GIVEN a custom thinking message
    const givenThinkingMessage = "Thinking about your response…";
    render(<TypingChatMessage waitBeforeThinking={0} thinkingMessage={givenThinkingMessage} />);

    // WHEN the thinking stage is reached
    act(() => {
      jest.advanceTimersByTime(1);
    });

    // THEN the custom thinking message is displayed
    expect(screen.getByText(givenThinkingMessage)).toBeInTheDocument();
    expect(screen.queryByText(i18n.t(UI_TEXT_KEYS.THINKING))).not.toBeInTheDocument();
  });

  test("should clear the stage timers when unmounted", () => {
    // GIVEN a rendered Typing Chat message
    const { unmount } = render(<TypingChatMessage />);

    // WHEN it is unmounted (the reply arrived)
    unmount();

    // THEN no timers are left pending
    expect(jest.getTimerCount()).toBe(0);
  });
});

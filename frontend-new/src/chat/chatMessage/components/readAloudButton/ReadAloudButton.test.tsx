// mute the console
import "src/_test_utilities/consoleMock";

import { act, render, screen, userEvent, waitFor, within } from "src/_test_utilities/test-utils";
import { StatusCodes } from "http-status-codes";
import ReadAloudButton, { DATA_TEST_ID } from "src/chat/chatMessage/components/readAloudButton/ReadAloudButton";
import { ReadAloudProvider } from "src/textToSpeech/ReadAloudContext";
import TextToSpeechService from "src/textToSpeech/TextToSpeechService";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";
import ChatList from "src/chat/chatList/ChatList";
import {
  generateAgentMessage,
  generateConversationConclusionMessage,
  generateErrorMessage,
  generateTypingMessage,
  generateUserMessage,
} from "src/chat/util";
import { SpeechEnvConfig } from "src/envService";
import i18n from "src/i18n/i18n";
import { ChatProvider } from "src/chat/ChatContext";

// the locale of the tests (see i18nMock)
const givenLocale = "en-US";
const givenMessageId = "message-1";
const givenOtherMessageId = "message-2";
const givenMessageOf = (messageId: string) => `The text of ${messageId}.`;

const givenSpeechConfig = (textToSpeech: Partial<SpeechEnvConfig["textToSpeech"]>): SpeechEnvConfig => ({
  speechToText: { enabled: false, locales: [], maxRecordingSeconds: 60 },
  textToSpeech: { enabled: true, locales: [givenLocale], maxTextBytes: 4000, ...textToSpeech },
});

describe("ReadAloudButton", () => {
  let synthesizeSpy: jest.SpyInstance;
  let pauseSpy: jest.SpyInstance;
  let playedAudio: HTMLMediaElement[];

  beforeEach(() => {
    jest.spyOn(require("src/envService"), "getSpeechConfig").mockReturnValue(givenSpeechConfig({}));
    jest.spyOn(require("src/envService"), "getBackendUrl").mockReturnValue("/api");
    synthesizeSpy = jest
      .spyOn(TextToSpeechService.prototype, "synthesize")
      .mockImplementation(async () => new Blob(["audio"], { type: "audio/mpeg" }));
    playedAudio = [];
    jest.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
      playedAudio.push(this);
      return Promise.resolve();
    });
    pauseSpy = jest.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    URL.createObjectURL = jest.fn(() => "blob:audio");
    URL.revokeObjectURL = jest.fn();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  const renderButtons = (...messageIds: string[]) =>
    render(
      <ReadAloudProvider>
        {messageIds.map((messageId) => (
          <div key={messageId} data-testid={`message-${messageId}`}>
            <ReadAloudButton messageId={messageId} message={givenMessageOf(messageId)} />
          </div>
        ))}
      </ReadAloudProvider>
    );

  const buttonOf = (messageId: string) =>
    within(screen.getByTestId(`message-${messageId}`)).getByTestId(DATA_TEST_ID.READ_ALOUD_BUTTON);

  describe("availability", () => {
    test.each([
      ["read aloud is off", givenSpeechConfig({ enabled: false })],
      ["read aloud is not offered in the locale", givenSpeechConfig({ locales: ["sw-KE"] })],
    ])("should not be shown when %s", (_d, givenConfig) => {
      // GIVEN the speech config
      jest.spyOn(require("src/envService"), "getSpeechConfig").mockReturnValue(givenConfig);

      // WHEN a message is rendered
      renderButtons(givenMessageId);

      // THEN expect no read aloud button
      expect(screen.queryByTestId(DATA_TEST_ID.READ_ALOUD_BUTTON)).not.toBeInTheDocument();
      // AND nothing to have been requested
      expect(synthesizeSpy).not.toHaveBeenCalled();
    });

    test("should not be shown outside a chat", () => {
      // WHEN the button is rendered without a read aloud player
      render(<ReadAloudButton messageId={givenMessageId} message={givenMessageOf(givenMessageId)} />);
      // THEN expect nothing
      expect(screen.queryByTestId(DATA_TEST_ID.READ_ALOUD_BUTTON)).not.toBeInTheDocument();
    });

    test("should be shown, idle, when read aloud is offered in the locale", () => {
      // WHEN a message is rendered
      renderButtons(givenMessageId);

      // THEN expect the read aloud button, with its label
      const actualButton = buttonOf(givenMessageId);
      expect(actualButton).toHaveAccessibleName(i18n.t("chat.readAloud.readAloudAriaLabel"));
      expect(within(actualButton).getByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).toBeInTheDocument();
      // AND no errors or warnings to have occurred
      expect(console.error).not.toHaveBeenCalled();
      expect(console.warn).not.toHaveBeenCalled();
    });
  });

  test("should read the message aloud when tapped, then stop at once when tapped again", async () => {
    // GIVEN a message
    renderButtons(givenMessageId);

    // WHEN the user taps the read aloud button
    await userEvent.click(buttonOf(givenMessageId));

    // THEN expect the message to be read, in the locale
    expect(synthesizeSpy).toHaveBeenCalledWith(givenMessageOf(givenMessageId), givenLocale, expect.any(AbortSignal));
    // AND the button to become a stop button
    await waitFor(() =>
      expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.STOP_READING_ICON)).toBeInTheDocument()
    );
    expect(buttonOf(givenMessageId)).toHaveAccessibleName(i18n.t("chat.readAloud.stopReadingAriaLabel"));

    // AND WHEN the user taps it again
    await userEvent.click(buttonOf(givenMessageId));

    // THEN expect the audio to have stopped
    expect(pauseSpy).toHaveBeenCalled();
    // AND the button to be idle again
    expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).toBeInTheDocument();
  });

  test("should show the loading state while the audio is prepared, and abort it when tapped", async () => {
    // GIVEN the audio takes a while
    synthesizeSpy.mockImplementation(() => new Promise<Blob>(() => {}));
    renderButtons(givenMessageId);

    // WHEN the user taps the read aloud button
    await userEvent.click(buttonOf(givenMessageId));

    // THEN expect the loading state
    expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.LOADING_ICON)).toBeInTheDocument();
    expect(buttonOf(givenMessageId)).toHaveAccessibleName(i18n.t("chat.readAloud.loadingAriaLabel"));

    // AND WHEN the user taps it again
    await userEvent.click(buttonOf(givenMessageId));

    // THEN expect the request to have been aborted
    expect((synthesizeSpy.mock.calls[0][2] as AbortSignal).aborted).toBe(true);
    // AND nothing to have been played
    expect(playedAudio).toHaveLength(0);
    // AND the button to be idle again
    expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).toBeInTheDocument();
  });

  test("should stop the first message when another one is read", async () => {
    // GIVEN the first of two messages is being read
    renderButtons(givenMessageId, givenOtherMessageId);
    await userEvent.click(buttonOf(givenMessageId));
    await waitFor(() =>
      expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.STOP_READING_ICON)).toBeInTheDocument()
    );

    // WHEN the user taps the read aloud button of the second one
    await userEvent.click(buttonOf(givenOtherMessageId));

    // THEN expect the second one to be read
    await waitFor(() =>
      expect(within(buttonOf(givenOtherMessageId)).getByTestId(DATA_TEST_ID.STOP_READING_ICON)).toBeInTheDocument()
    );
    // AND the first one to be idle again
    expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).toBeInTheDocument();
    // AND the request of the first one to have been aborted
    expect((synthesizeSpy.mock.calls[0][2] as AbortSignal).aborted).toBe(true);
  });

  test("should return to idle when the message has been read", async () => {
    // GIVEN a message is being read
    renderButtons(givenMessageId);
    await userEvent.click(buttonOf(givenMessageId));
    await waitFor(() => expect(playedAudio).toHaveLength(1));

    // WHEN the audio ends
    act(() => playedAudio[0].dispatchEvent(new Event("ended")));

    // THEN expect the button to be idle again
    await waitFor(() =>
      expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).toBeInTheDocument()
    );
  });

  test.each([
    ["rate limited", StatusCodes.TOO_MANY_REQUESTS, i18n.t("chat.readAloud.errors.rateLimited")],
    ["the service failed", StatusCodes.BAD_GATEWAY, i18n.t("chat.readAloud.errors.unavailable")],
  ])("should tell the user when %s, and stay usable", async (_d, givenStatus, expectedMessage) => {
    // GIVEN reading aloud fails
    synthesizeSpy.mockRejectedValueOnce(
      new RestAPIError(
        "TextToSpeechService",
        "synthesize",
        "POST",
        "/",
        givenStatus,
        ErrorConstants.ErrorCodes.API_ERROR,
        "x"
      )
    );
    renderButtons(givenMessageId);

    // WHEN the user taps the read aloud button
    await userEvent.click(buttonOf(givenMessageId));

    // THEN expect the error to be shown
    expect(await screen.findByText(expectedMessage)).toBeInTheDocument();
    // AND the button to be idle, so the user can try again
    expect(within(buttonOf(givenMessageId)).getByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).toBeInTheDocument();
  });

  test("should tell the user when the browser blocks the audio", async () => {
    // GIVEN the browser does not let the audio play
    jest
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockRejectedValue(new DOMException("not allowed", "NotAllowedError"));
    renderButtons(givenMessageId);

    // WHEN the user taps the read aloud button
    await userEvent.click(buttonOf(givenMessageId));

    // THEN expect the autoplay error to be shown
    expect(await screen.findByText(i18n.t("chat.readAloud.errors.autoplayBlocked"))).toBeInTheDocument();
  });

  describe("message types", () => {
    test("should be shown on AI messages only", () => {
      // GIVEN a chat with every kind of message
      const givenAgentText = "I am the assistant.";
      const givenAgentMessage = generateAgentMessage("agent-1", givenAgentText, new Date().toISOString());
      const givenMessages = [
        generateUserMessage("I am the user.", new Date().toISOString(), "#000", "#fff"),
        givenAgentMessage,
        generateErrorMessage("Something went wrong."),
        generateTypingMessage(),
        generateConversationConclusionMessage("conclusion-1", "Thank you for the conversation."),
      ];

      // WHEN the chat is rendered
      render(
        <ChatProvider
          handleOpenExperiencesDrawer={jest.fn()}
          removeMessageFromChat={jest.fn()}
          addMessageToChat={jest.fn()}
        >
          <ChatList messages={givenMessages} />
        </ChatProvider>
      );

      // THEN expect one read aloud button, for the AI message
      const actualButtons = screen.getAllByTestId(DATA_TEST_ID.READ_ALOUD_BUTTON);
      expect(actualButtons).toHaveLength(1);
      expect(screen.getByText(givenAgentText).closest("li")).toContainElement(actualButtons[0]);
    });
  });
});

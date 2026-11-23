// mute the console
import "src/_test_utilities/consoleMock";

import { render, screen, userEvent, waitFor } from "src/_test_utilities/test-utils";
import { StatusCodes } from "http-status-codes";
import ChatMessageField, {
  CHAT_MESSAGE_MAX_LENGTH,
  ChatMessageFieldProps,
  DATA_TEST_ID,
} from "src/chat/ChatMessageField/ChatMessageField";
import { DATA_TEST_ID as WAVEFORM_DATA_TEST_ID } from "src/chat/ChatMessageField/recordingWaveform/RecordingWaveform";
import SpeechToTextService from "src/speechToText/SpeechToTextService";
import { SpeechEnvConfig } from "src/envService";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";
import { mockBrowserIsOnLine, unmockBrowserIsOnLine } from "src/_test_utilities/mockBrowserIsOnline";
import {
  FakeMediaRecorder,
  installMediaRecorderMock,
  MediaRecorderMock,
  uninstallMediaRecorderMock,
} from "src/_test_utilities/mediaRecorderMock";
import i18n from "src/i18n/i18n";

// the locale of the tests (see i18nMock)
const givenLocale = "en-US";
const givenTranscript = "I worked as a carpenter for three years";

const givenSpeechConfig = (speechToText: Partial<SpeechEnvConfig["speechToText"]> = {}): SpeechEnvConfig => ({
  speechToText: { enabled: true, locales: [givenLocale], maxRecordingSeconds: 60, ...speechToText },
  textToSpeech: { enabled: false, locales: [], maxTextBytes: 4000 },
});

const givenRestAPIError = (statusCode: number) =>
  new RestAPIError(
    "SpeechToTextService",
    "transcribe",
    "POST",
    "/",
    statusCode,
    ErrorConstants.ErrorCodes.API_ERROR,
    "x"
  );

describe("ChatMessageField voice input", () => {
  let media: MediaRecorderMock;
  let transcribeSpy: jest.SpyInstance;

  beforeEach(() => {
    unmockBrowserIsOnLine();
    jest.spyOn(require("src/envService"), "getSpeechConfig").mockReturnValue(givenSpeechConfig());
    jest.spyOn(require("src/envService"), "getCvUploadEnabled").mockReturnValue("false");
    jest.spyOn(require("src/envService"), "getBackendUrl").mockReturnValue("/api");
    media = installMediaRecorderMock();
    transcribeSpy = jest
      .spyOn(SpeechToTextService.prototype, "transcribe")
      .mockResolvedValue({ text: givenTranscript, locale: givenLocale });
    jest.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);
    jest.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
  });

  afterEach(() => {
    uninstallMediaRecorderMock();
    jest.clearAllMocks();
  });

  const givenProps = (props: Partial<ChatMessageFieldProps> = {}): ChatMessageFieldProps => ({
    handleSend: jest.fn(),
    aiIsTyping: false,
    isChatFinished: false,
    ...props,
  });

  const micButton = () => screen.getByTestId(DATA_TEST_ID.CHAT_MESSAGE_FIELD_MIC_BUTTON);
  const field = (): HTMLTextAreaElement => screen.getByTestId(DATA_TEST_ID.CHAT_MESSAGE_FIELD);
  const sendButton = () => screen.getByTestId(DATA_TEST_ID.CHAT_MESSAGE_FIELD_SEND_BUTTON);

  const record = async () => {
    await userEvent.click(micButton());
    await screen.findByTestId(DATA_TEST_ID.CHAT_MESSAGE_FIELD_STOP_RECORDING_ICON);
  };

  const recordAndStop = async () => {
    await record();
    await userEvent.click(micButton());
    await waitFor(() => expect(screen.queryByTestId(WAVEFORM_DATA_TEST_ID.RECORDING_WAVEFORM)).not.toBeInTheDocument());
  };

  describe("availability", () => {
    test.each([
      ["voice input is off", () => givenSpeechConfig({ enabled: false }), () => {}],
      ["voice input is not offered in the locale", () => givenSpeechConfig({ locales: ["sw-KE"] }), () => {}],
      [
        "the browser cannot record",
        () => givenSpeechConfig(),
        () => Object.defineProperty(window, "MediaRecorder", { value: undefined, configurable: true }),
      ],
      [
        "the browser cannot use the microphone",
        () => givenSpeechConfig(),
        () => Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true }),
      ],
    ])("should not show the mic when %s", (_d, givenConfig, givenBrowser) => {
      // GIVEN the config and the browser
      jest.spyOn(require("src/envService"), "getSpeechConfig").mockReturnValue(givenConfig());
      givenBrowser();

      // WHEN the field is rendered
      render(<ChatMessageField {...givenProps()} />);

      // THEN expect no mic button
      expect(screen.queryByTestId(DATA_TEST_ID.CHAT_MESSAGE_FIELD_MIC_BUTTON)).not.toBeInTheDocument();
    });

    test("should show the mic when voice input is offered in the locale and the browser can record", () => {
      // WHEN the field is rendered
      render(<ChatMessageField {...givenProps()} />);

      // THEN expect the mic button, with its label
      expect(micButton()).toHaveAccessibleName(i18n.t("chat.voiceInput.startRecordingAriaLabel"));
      expect(screen.getByTestId(DATA_TEST_ID.CHAT_MESSAGE_FIELD_MIC_ICON)).toBeInTheDocument();
      // AND no errors or warnings to have occurred
      expect(console.error).not.toHaveBeenCalled();
      expect(console.warn).not.toHaveBeenCalled();
    });

    test.each([
      ["the AI is typing", givenProps({ aiIsTyping: true })],
      ["the conversation has finished", givenProps({ isChatFinished: true })],
      ["the input is disabled", givenProps({ isInputDisabled: true })],
      ["a CV is uploading", givenProps({ isUploadingCv: true })],
    ])("should disable the mic when %s", (_d, givenFieldProps) => {
      // WHEN the field is rendered
      render(<ChatMessageField {...givenFieldProps} />);
      // THEN expect the mic to be disabled
      expect(micButton()).toBeDisabled();
    });

    test("should disable the mic when offline", () => {
      // GIVEN the browser is offline
      mockBrowserIsOnLine(false);
      // WHEN the field is rendered
      render(<ChatMessageField {...givenProps()} />);
      // THEN expect the mic to be disabled
      expect(micButton()).toBeDisabled();
    });
  });

  test("should show the level graph while recording, then put the transcript in the field", async () => {
    // GIVEN the field
    const givenFieldProps = givenProps();
    render(<ChatMessageField {...givenFieldProps} />);

    // WHEN the user taps the mic
    await record();

    // THEN expect the level graph and the elapsed time in the field
    expect(screen.getByTestId(WAVEFORM_DATA_TEST_ID.RECORDING_WAVEFORM)).toBeInTheDocument();
    expect(screen.getByTestId(WAVEFORM_DATA_TEST_ID.RECORDING_ELAPSED_TIME)).toBeInTheDocument();
    // AND the mic to have become a stop button
    expect(micButton()).toHaveAccessibleName(i18n.t("chat.voiceInput.stopRecordingAriaLabel"));
    // AND the text not to be editable, nor sendable
    expect(field()).toHaveAttribute("readonly");
    expect(sendButton()).toBeDisabled();
    // AND nothing to have been sent while recording
    expect(transcribeSpy).not.toHaveBeenCalled();

    // AND WHEN the user taps stop
    await userEvent.click(micButton());

    // THEN expect exactly one transcribe call
    expect(transcribeSpy).toHaveBeenCalledTimes(1);
    // AND the transcript to be put in the field
    await waitFor(() => expect(field()).toHaveValue(givenTranscript));
    // AND the field to be editable again
    expect(field()).not.toHaveAttribute("readonly");
    expect(screen.queryByTestId(WAVEFORM_DATA_TEST_ID.RECORDING_WAVEFORM)).not.toBeInTheDocument();
    // AND the microphone to have been released
    expect(media.streams[0].tracks[0].stop).toHaveBeenCalled();

    // AND WHEN the user edits the text and sends it
    const givenEdit = " at a workshop";
    await userEvent.type(field(), givenEdit);
    await userEvent.click(sendButton());

    // THEN expect it to be sent as typed text
    expect(givenFieldProps.handleSend).toHaveBeenCalledWith(`${givenTranscript}${givenEdit}`);
  });

  test("should focus the field once the transcript is in it, so the user can review it", async () => {
    // GIVEN the field
    render(<ChatMessageField {...givenProps()} />);
    // AND whether the field is visible each time it is focused (a browser ignores focusing a hidden one)
    const actualFocusVisibility: boolean[] = [];
    const focusSpy = jest.spyOn(HTMLTextAreaElement.prototype, "focus").mockImplementation(function (
      this: HTMLTextAreaElement
    ) {
      actualFocusVisibility.push(this.style.display !== "none");
    });

    // WHEN the user records and stops
    await recordAndStop();

    // THEN expect the transcript in the field
    await waitFor(() => expect(field()).toHaveValue(givenTranscript));
    // AND the field to have been focused while visible, not while still hidden behind the level graph
    expect(actualFocusVisibility).toEqual([true]);
    focusSpy.mockRestore();
  });

  test("should show the transcribing state while the recording is transcribed", async () => {
    // GIVEN the transcription takes a while
    transcribeSpy.mockImplementation(() => new Promise(() => {}));
    render(<ChatMessageField {...givenProps()} />);
    await record();

    // WHEN the user taps stop
    await userEvent.click(micButton());

    // THEN expect the transcribing state
    expect(screen.getByTestId(WAVEFORM_DATA_TEST_ID.RECORDING_TRANSCRIBING)).toBeInTheDocument();
    // AND the mic and send to be disabled
    expect(micButton()).toBeDisabled();
    expect(sendButton()).toBeDisabled();
  });

  test("should append the transcript to the text typed before recording, with a space", async () => {
    // GIVEN the user typed some text, with a trailing space
    render(<ChatMessageField {...givenProps()} />);
    const givenTypedText = "Hello.";
    await userEvent.type(field(), `${givenTypedText} `);

    // WHEN the user records and stops
    await recordAndStop();

    // THEN expect the typed text to be kept, followed by the transcript
    await waitFor(() => expect(field()).toHaveValue(`${givenTypedText} ${givenTranscript}`));
  });

  test("should show the existing error when the transcript makes the message too long", async () => {
    // GIVEN the user typed text close to the limit
    render(<ChatMessageField {...givenProps()} />);
    await userEvent.click(field());
    await userEvent.paste("a".repeat(CHAT_MESSAGE_MAX_LENGTH - 10));

    // WHEN the transcript is added
    await recordAndStop();

    // THEN expect the message limit error
    expect(
      await screen.findByText(i18n.t("common.chat.errors.messageLimit", { max: CHAT_MESSAGE_MAX_LENGTH }))
    ).toBeInTheDocument();
    // AND the message not to be sendable
    expect(sendButton()).toBeDisabled();
  });

  test("should remove disallowed characters from the transcript, as from typed text", async () => {
    // GIVEN a transcript with disallowed characters
    const givenTranscriptWithDisallowedCharacters = "I use {curly} <tags>";
    transcribeSpy.mockResolvedValue({ text: givenTranscriptWithDisallowedCharacters, locale: givenLocale });
    render(<ChatMessageField {...givenProps()} />);

    // WHEN the transcript is added
    await recordAndStop();

    // THEN expect the characters to be removed
    await waitFor(() => expect(field()).toHaveValue(givenTranscriptWithDisallowedCharacters.replace(/[{}<>]/g, "")));
    // AND the invalid characters error to be shown
    expect(
      screen.getByText(i18n.t("common.chat.errors.invalidSpecialCharacters", { chars: "{,},<,>" }))
    ).toBeInTheDocument();
  });

  test("should start one recording when the mic is double-tapped", async () => {
    // GIVEN the field
    render(<ChatMessageField {...givenProps()} />);

    // WHEN the user double-taps the mic
    await userEvent.dblClick(micButton());

    // THEN expect one recording
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBeGreaterThan(0));
    expect(media.getUserMedia).toHaveBeenCalledTimes(1);
  });

  test("should drop the recording when the field gets disabled", async () => {
    // GIVEN the user is recording
    const { rerender } = render(<ChatMessageField {...givenProps()} />);
    await record();

    // WHEN the field gets disabled
    rerender(<ChatMessageField {...givenProps({ aiIsTyping: true })} />);

    // THEN expect the recording to have stopped, and the microphone to be released
    await waitFor(() => expect(media.streams[0].tracks[0].stop).toHaveBeenCalled());
    expect(screen.queryByTestId(WAVEFORM_DATA_TEST_ID.RECORDING_WAVEFORM)).not.toBeInTheDocument();
    // AND nothing to be transcribed
    expect(transcribeSpy).not.toHaveBeenCalled();
  });

  test("should drop the recording when the locale is switched", async () => {
    // GIVEN the user is recording
    const actualReactI18next = jest.requireMock("react-i18next");
    const originalUseTranslation = actualReactI18next.useTranslation;
    const { rerender } = render(<ChatMessageField {...givenProps()} />);
    await record();

    // WHEN the user switches the locale
    const useTranslationSpy = jest.spyOn(actualReactI18next, "useTranslation").mockImplementation(() => {
      const translation = originalUseTranslation();
      return { ...translation, i18n: { ...translation.i18n, language: "sw-KE" } };
    });
    rerender(<ChatMessageField {...givenProps()} />);

    // THEN expect the recording to have stopped cleanly, without being transcribed
    await waitFor(() => expect(media.streams[0].tracks[0].stop).toHaveBeenCalled());
    expect(transcribeSpy).not.toHaveBeenCalled();
    // AND the mic to be gone, as voice input is not offered in the new locale
    expect(screen.queryByTestId(DATA_TEST_ID.CHAT_MESSAGE_FIELD_MIC_BUTTON)).not.toBeInTheDocument();
    useTranslationSpy.mockRestore();
  });

  test("should release the microphone when the field unmounts while recording", async () => {
    // GIVEN the user is recording
    const { unmount } = render(<ChatMessageField {...givenProps()} />);
    await record();

    // WHEN the field unmounts
    unmount();

    // THEN expect the microphone to be released
    expect(media.streams[0].tracks[0].stop).toHaveBeenCalled();
    expect(transcribeSpy).not.toHaveBeenCalled();
  });

  describe("errors", () => {
    test.each([
      [
        "the microphone is refused",
        new DOMException("denied", "NotAllowedError"),
        "chat.voiceInput.errors.permissionDenied",
      ],
      ["there is no microphone", new DOMException("none", "NotFoundError"), "chat.voiceInput.errors.noMicrophone"],
    ] as const)("should tell the user when %s, and stay usable", async (_d, givenError, expectedMessageKey) => {
      // GIVEN the microphone cannot be used
      media.getUserMedia.mockRejectedValueOnce(givenError);
      render(<ChatMessageField {...givenProps()} />);

      // WHEN the user taps the mic
      await userEvent.click(micButton());

      // THEN expect the error to be shown
      expect(await screen.findByText(i18n.t(expectedMessageKey))).toBeInTheDocument();
      // AND the field to stay usable
      const givenTypedText = "typed instead";
      await userEvent.type(field(), givenTypedText);
      expect(field()).toHaveValue(givenTypedText);
      expect(micButton()).toBeEnabled();
    });

    test.each([
      [
        "no speech is recognized",
        givenRestAPIError(StatusCodes.UNPROCESSABLE_ENTITY),
        "chat.voiceInput.errors.noSpeech",
      ],
      [
        "the user is rate limited",
        givenRestAPIError(StatusCodes.TOO_MANY_REQUESTS),
        "chat.voiceInput.errors.rateLimited",
      ],
      ["the service fails", givenRestAPIError(StatusCodes.BAD_GATEWAY), "chat.voiceInput.errors.unavailable"],
      [
        "the request does not reach the backend",
        new RestAPIError("S", "f", "POST", "/", 0, ErrorConstants.ErrorCodes.FAILED_TO_FETCH, "x"),
        "chat.voiceInput.errors.network",
      ],
    ] as const)("should tell the user when %s, keeping the typed text", async (_d, givenError, expectedMessageKey) => {
      // GIVEN transcribing fails
      transcribeSpy.mockRejectedValueOnce(givenError);
      render(<ChatMessageField {...givenProps()} />);
      const givenTypedText = "Typed first";
      await userEvent.type(field(), givenTypedText);

      // WHEN the user records and stops
      await recordAndStop();

      // THEN expect the error to be shown
      expect(await screen.findByText(i18n.t(expectedMessageKey))).toBeInTheDocument();
      // AND the typed text to be kept, and editable
      expect(field()).toHaveValue(givenTypedText);
      expect(field()).not.toHaveAttribute("readonly");
    });

    test("should clear the error when the user records again", async () => {
      // GIVEN a recording failed
      transcribeSpy.mockRejectedValueOnce(givenRestAPIError(StatusCodes.BAD_GATEWAY));
      render(<ChatMessageField {...givenProps()} />);
      await recordAndStop();
      await screen.findByText(i18n.t("chat.voiceInput.errors.unavailable"));

      // WHEN the user records again
      await record();

      // THEN expect the error to be gone
      expect(screen.queryByText(i18n.t("chat.voiceInput.errors.unavailable"))).not.toBeInTheDocument();
    });
  });
});

// mute the console
import "src/_test_utilities/consoleMock";

import { render, screen, fireEvent } from "src/_test_utilities/test-utils";
import ReadAloudButton, { DATA_TEST_ID } from "./ReadAloudButton";
import { useTextToSpeech } from "src/textToSpeech/useTextToSpeech";
import { getTextToSpeechEnabled } from "src/envService";
import { TextToSpeechStatus } from "src/textToSpeech/useTextToSpeech";

// --- Mocks ---

jest.mock("src/textToSpeech/useTextToSpeech", () => ({
  useTextToSpeech: jest.fn(),
}));

jest.mock("src/envService", () => ({
  ...jest.requireActual("src/envService"),
  getTextToSpeechEnabled: jest.fn(),
}));

const mockSpeak = jest.fn();
const mockStop = jest.fn();
const mockUseTextToSpeech = useTextToSpeech as jest.MockedFunction<typeof useTextToSpeech>;
const mockGetTextToSpeechEnabled = getTextToSpeechEnabled as jest.MockedFunction<typeof getTextToSpeechEnabled>;

function setupMocks(overrides: { status?: TextToSpeechStatus; isSupported?: boolean; ttsEnabled?: string } = {}) {
  const { status = "idle", isSupported = true, ttsEnabled = "true" } = overrides;
  mockGetTextToSpeechEnabled.mockReturnValue(ttsEnabled);
  mockUseTextToSpeech.mockReturnValue({
    status,
    speak: mockSpeak,
    stop: mockStop,
    isSupported,
  });
}

describe("ReadAloudButton", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("should render nothing when TTS is disabled", () => {
    // GIVEN text-to-speech is disabled via configuration
    setupMocks({ ttsEnabled: "false" });

    // WHEN the ReadAloudButton is rendered
    const { container } = render(<ReadAloudButton messageText="Hello" />);

    // THEN expect nothing to be rendered
    expect(container.innerHTML).toBe("");
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should render nothing when not supported", () => {
    // GIVEN text-to-speech is enabled but not supported
    setupMocks({ isSupported: false });

    // WHEN the ReadAloudButton is rendered
    const { container } = render(<ReadAloudButton messageText="Hello" />);

    // THEN expect nothing to be rendered
    expect(container.innerHTML).toBe("");
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should render volume icon when idle", () => {
    // GIVEN text-to-speech is enabled and the status is idle
    setupMocks({ status: "idle" });

    // WHEN the ReadAloudButton is rendered
    render(<ReadAloudButton messageText="Hello" />);

    // THEN expect the read aloud (volume) icon to be visible
    expect(screen.getByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).toBeInTheDocument();
    // AND expect the stop and loading icons not to be present
    expect(screen.queryByTestId(DATA_TEST_ID.STOP_READING_ICON)).not.toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.LOADING_ICON)).not.toBeInTheDocument();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should render loading spinner when loading", () => {
    // GIVEN text-to-speech is enabled and the status is loading
    setupMocks({ status: "loading" });

    // WHEN the ReadAloudButton is rendered
    render(<ReadAloudButton messageText="Hello" />);

    // THEN expect the loading icon to be visible
    expect(screen.getByTestId(DATA_TEST_ID.LOADING_ICON)).toBeInTheDocument();
    // AND expect the volume and stop icons not to be present
    expect(screen.queryByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).not.toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.STOP_READING_ICON)).not.toBeInTheDocument();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should render stop icon when playing", () => {
    // GIVEN text-to-speech is enabled and the status is playing
    setupMocks({ status: "playing" });

    // WHEN the ReadAloudButton is rendered
    render(<ReadAloudButton messageText="Hello" />);

    // THEN expect the stop reading icon to be visible
    expect(screen.getByTestId(DATA_TEST_ID.STOP_READING_ICON)).toBeInTheDocument();
    // AND expect the volume and loading icons not to be present
    expect(screen.queryByTestId(DATA_TEST_ID.READ_ALOUD_ICON)).not.toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.LOADING_ICON)).not.toBeInTheDocument();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should call speak when clicking in idle state", async () => {
    // GIVEN text-to-speech is enabled and the status is idle
    const givenMessageText = "Hello world";
    setupMocks({ status: "idle" });

    // WHEN the ReadAloudButton is rendered
    render(<ReadAloudButton messageText={givenMessageText} />);

    // AND the button is clicked
    const actualButton = screen.getByTestId(DATA_TEST_ID.READ_ALOUD_BUTTON);
    fireEvent.click(actualButton);

    // THEN expect speak to have been called with the message text
    expect(mockSpeak).toHaveBeenCalledWith(givenMessageText);
    // AND expect stop not to have been called
    expect(mockStop).not.toHaveBeenCalled();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should call stop when clicking in playing state", () => {
    // GIVEN text-to-speech is enabled and the status is playing
    setupMocks({ status: "playing" });

    // WHEN the ReadAloudButton is rendered
    render(<ReadAloudButton messageText="Hello" />);

    // AND the button is clicked
    const actualButton = screen.getByTestId(DATA_TEST_ID.READ_ALOUD_BUTTON);
    fireEvent.click(actualButton);

    // THEN expect stop to have been called
    expect(mockStop).toHaveBeenCalled();
    // AND expect speak not to have been called
    expect(mockSpeak).not.toHaveBeenCalled();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should disable button during loading", () => {
    // GIVEN text-to-speech is enabled and the status is loading
    setupMocks({ status: "loading" });

    // WHEN the ReadAloudButton is rendered
    render(<ReadAloudButton messageText="Hello" />);

    // THEN expect the button to be disabled
    const actualButton = screen.getByTestId(DATA_TEST_ID.READ_ALOUD_BUTTON);
    expect(actualButton).toBeDisabled();
    // AND expect no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });
});

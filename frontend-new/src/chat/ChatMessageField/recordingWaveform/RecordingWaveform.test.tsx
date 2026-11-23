// mute the console
import "src/_test_utilities/consoleMock";

import { act, render, screen } from "src/_test_utilities/test-utils";
import RecordingWaveform, {
  DATA_TEST_ID,
  DEFAULT_VISIBLE_BARS,
  REDUCED_MOTION_QUERY,
} from "src/chat/ChatMessageField/recordingWaveform/RecordingWaveform";
import i18n from "src/i18n/i18n";

const givenReducedMotion = (reduced: boolean) =>
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: jest.fn((query: string) => ({
      matches: reduced && query === REDUCED_MOTION_QUERY,
      media: query,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    })),
  });

describe("RecordingWaveform", () => {
  beforeEach(() => givenReducedMotion(false));
  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  test("should show bars that follow the audio level, and the elapsed time, while recording", () => {
    // GIVEN a recording that started 1 minute and 5 seconds ago
    const givenNow = 100_000;
    const givenElapsedMs = 65_000;
    jest.spyOn(Date, "now").mockReturnValue(givenNow);
    // AND getting louder
    const givenLevels = [0, 0.5, 1];

    // WHEN it is shown
    render(<RecordingWaveform status="recording" startedAt={givenNow - givenElapsedMs} levels={givenLevels} />);

    // THEN expect the bars to end with the given levels, the newest on the right
    const actualBars = screen.getAllByTestId(DATA_TEST_ID.RECORDING_WAVEFORM_BAR);
    expect(actualBars).toHaveLength(DEFAULT_VISIBLE_BARS);
    expect(actualBars.slice(-givenLevels.length).map((bar) => bar.getAttribute("data-level"))).toEqual(
      givenLevels.map((level) => level.toFixed(2))
    );
    // AND the elapsed time, as minutes and seconds
    const expectedElapsedTime = "1:05";
    expect(screen.getByTestId(DATA_TEST_ID.RECORDING_ELAPSED_TIME)).toHaveTextContent(expectedElapsedTime);
    // AND screen readers to be told that it is recording
    expect(screen.getByRole("status")).toHaveTextContent(i18n.t("chat.voiceInput.recording"));
    // AND no errors or warnings to have occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should count the elapsed time up", () => {
    // GIVEN a recording that just started
    jest.useFakeTimers();
    const givenStartedAt = 0;
    const dateNowSpy = jest.spyOn(Date, "now").mockReturnValue(givenStartedAt);
    render(<RecordingWaveform status="recording" startedAt={givenStartedAt} levels={[]} />);
    expect(screen.getByTestId(DATA_TEST_ID.RECORDING_ELAPSED_TIME)).toHaveTextContent("0:00");

    // WHEN 3 seconds pass
    const givenElapsedSeconds = 3;
    dateNowSpy.mockReturnValue(givenStartedAt + givenElapsedSeconds * 1000);
    act(() => jest.advanceTimersByTime(250));

    // THEN expect the elapsed time to have moved
    expect(screen.getByTestId(DATA_TEST_ID.RECORDING_ELAPSED_TIME)).toHaveTextContent(`0:0${givenElapsedSeconds}`);
  });

  test("should show a static indicator instead of moving bars when the user prefers reduced motion", () => {
    // GIVEN the user prefers reduced motion
    givenReducedMotion(true);

    // WHEN a recording is shown
    render(<RecordingWaveform status="recording" startedAt={Date.now()} levels={[0.4]} />);

    // THEN expect the static indicator, and no bars
    expect(screen.getByTestId(DATA_TEST_ID.RECORDING_STATIC_INDICATOR)).toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.RECORDING_WAVEFORM_BAR)).not.toBeInTheDocument();
  });

  test("should show the transcribing state after the recording", () => {
    // WHEN the recording is being transcribed
    render(<RecordingWaveform status="transcribing" />);

    // THEN expect the transcribing state, without bars or time
    expect(screen.getByTestId(DATA_TEST_ID.RECORDING_TRANSCRIBING)).toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.RECORDING_WAVEFORM_BAR)).not.toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.RECORDING_ELAPSED_TIME)).not.toBeInTheDocument();
    // AND screen readers to be told
    expect(screen.getByRole("status")).toHaveTextContent(i18n.t("chat.voiceInput.transcribing"));
  });
});

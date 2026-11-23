// mute the console
import "src/_test_utilities/consoleMock";

import { act, renderHook, waitFor } from "src/_test_utilities/test-utils";
import { StatusCodes } from "http-status-codes";
import SpeechToTextService from "src/speechToText/SpeechToTextService";
import {
  isVoiceInputSupported,
  LEVEL_SAMPLE_INTERVAL_MS,
  useSpeechToText,
  UseSpeechToTextOptions,
} from "src/speechToText/useSpeechToText";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";
import {
  FakeAnalyserNode,
  FakeAudioContext,
  FakeMediaRecorder,
  installMediaRecorderMock,
  MediaRecorderMock,
  uninstallMediaRecorderMock,
} from "src/_test_utilities/mediaRecorderMock";

const givenLocale = "en-US";
const givenTranscript = "I worked as a carpenter for three years.";

const givenRestAPIError = (statusCode: number, errorCode = ErrorConstants.ErrorCodes.API_ERROR) =>
  new RestAPIError(
    "SpeechToTextService",
    "transcribe",
    "POST",
    "/speech-to-text/transcribe",
    statusCode,
    errorCode,
    "x"
  );

describe("useSpeechToText", () => {
  let media: MediaRecorderMock;
  let transcribeSpy: jest.SpyInstance;
  let animationFrames: Map<number, FrameRequestCallback>;

  beforeEach(() => {
    jest.spyOn(require("src/envService"), "getBackendUrl").mockReturnValue("/api");
    media = installMediaRecorderMock();
    transcribeSpy = jest
      .spyOn(SpeechToTextService.prototype, "transcribe")
      .mockResolvedValue({ text: givenTranscript, locale: givenLocale });
    animationFrames = new Map();
    let nextFrame = 0;
    jest.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      animationFrames.set(++nextFrame, callback);
      return nextFrame;
    });
    jest.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => animationFrames.delete(id));
  });

  afterEach(() => {
    uninstallMediaRecorderMock();
    jest.clearAllMocks();
    jest.useRealTimers();
  });

  /** Runs the pending animation frames at the given time. */
  const runAnimationFrames = (now: number) =>
    act(() => {
      const callbacks = Array.from(animationFrames.values());
      animationFrames.clear();
      callbacks.forEach((callback) => callback(now));
    });

  const renderVoiceInput = (options: Partial<UseSpeechToTextOptions> = {}) => {
    const onTranscript = jest.fn();
    const onError = jest.fn();
    const view = renderHook(() =>
      useSpeechToText({ locale: givenLocale, maxRecordingSeconds: 60, onTranscript, onError, ...options })
    );
    return { ...view, onTranscript, onError };
  };

  const startRecording = async (result: { current: ReturnType<typeof useSpeechToText> }) => {
    act(() => result.current.start());
    await waitFor(() => expect(result.current.state.status).toBe("recording"));
  };

  test("should be supported when the browser can record the microphone", () => {
    // GIVEN getUserMedia and MediaRecorder
    // THEN expect voice input to be supported
    expect(isVoiceInputSupported()).toBe(true);
  });

  test.each([
    ["MediaRecorder", () => Object.defineProperty(window, "MediaRecorder", { value: undefined, configurable: true })],
    ["getUserMedia", () => Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true })],
  ])("should not be supported without %s", (_d, givenRemoveApi) => {
    // GIVEN the browser lacks the API
    givenRemoveApi();
    // THEN expect voice input not to be supported
    expect(isVoiceInputSupported()).toBe(false);
  });

  test("should record, then transcribe the recording once when stopped", async () => {
    // GIVEN a browser that records Opus in WebM, as Chrome and Firefox
    const givenMimeType = "audio/webm;codecs=opus";
    FakeMediaRecorder.supportedMimeTypes = [givenMimeType, "audio/webm"];
    // AND voice input
    const { result, onTranscript } = renderVoiceInput();

    // WHEN the user starts recording
    await startRecording(result);

    // THEN expect the microphone to have been asked for
    expect(media.getUserMedia).toHaveBeenCalledWith({ audio: true });
    // AND the best supported format to be recorded
    expect(FakeMediaRecorder.instances[0].mimeType).toBe(givenMimeType);
    // AND nothing to have been sent while recording
    expect(transcribeSpy).not.toHaveBeenCalled();

    // AND WHEN the user stops
    act(() => result.current.stop());

    // THEN expect the recording to be transcribed once, in the locale
    expect(result.current.state).toEqual({ status: "transcribing" });
    expect(transcribeSpy).toHaveBeenCalledTimes(1);
    const [actualRecording, actualLocale] = transcribeSpy.mock.calls[0];
    expect(actualRecording.size).toBeGreaterThan(0);
    expect(actualLocale).toBe(givenLocale);
    // AND the transcript to be given
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith(givenTranscript));
    expect(result.current.state).toEqual({ status: "idle" });
    // AND the microphone to have been released
    expect(media.streams[0].tracks[0].stop).toHaveBeenCalled();
    // AND the audio context to have been closed
    expect(FakeAudioContext.instances[0].closed).toBe(true);
  });

  test("should pick the MP4 format when the browser cannot record WebM, as Safari", async () => {
    // GIVEN a browser that only records MP4
    const givenMimeType = "audio/mp4";
    FakeMediaRecorder.supportedMimeTypes = [givenMimeType];
    const { result } = renderVoiceInput();

    // WHEN the user starts recording
    await startRecording(result);

    // THEN expect MP4 to be recorded
    expect(FakeMediaRecorder.instances[0].mimeType).toBe(givenMimeType);
  });

  test("should follow the audio level while recording", async () => {
    // GIVEN the user is recording in silence
    const givenSilence = 128;
    const givenLoudest = 255;
    FakeAnalyserNode.waveformValue = givenSilence;
    const { result } = renderVoiceInput();
    await startRecording(result);
    const givenNow = 1000;
    runAnimationFrames(givenNow);
    const expectedSilentLevel = 0;
    expect(result.current.levels).toEqual([expectedSilentLevel]);

    // WHEN the user speaks loudly, a sample interval later
    FakeAnalyserNode.waveformValue = givenLoudest;
    runAnimationFrames(givenNow + LEVEL_SAMPLE_INTERVAL_MS);

    // THEN expect a new level, close to the loudest
    expect(result.current.levels).toHaveLength(2);
    expect(result.current.levels[1]).toBeGreaterThan(0.9);

    // AND WHEN the recording stops
    act(() => result.current.stop());

    // THEN expect the levels to be cleared, and the animation loop to have stopped
    expect(result.current.levels).toEqual([]);
    expect(animationFrames.size).toBe(0);
  });

  test("should not start two recordings when the mic is tapped twice", async () => {
    // GIVEN voice input
    const { result } = renderVoiceInput();

    // WHEN the user taps the mic twice quickly
    act(() => {
      result.current.start();
      result.current.start();
    });
    await waitFor(() => expect(result.current.state.status).toBe("recording"));

    // THEN expect one recording
    expect(media.getUserMedia).toHaveBeenCalledTimes(1);
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });

  test("should stop by itself at the longest recording time", async () => {
    // GIVEN a limit of 5 seconds
    jest.useFakeTimers();
    const { result } = renderVoiceInput({ maxRecordingSeconds: 5 });
    await startRecording(result);

    // WHEN 5 seconds pass
    act(() => jest.advanceTimersByTime(5000));

    // THEN expect the recording to have stopped and to be transcribed
    expect(FakeMediaRecorder.instances[0].stop).toHaveBeenCalled();
    expect(transcribeSpy).toHaveBeenCalledTimes(1);
  });

  test.each([
    ["the user refuses the microphone", new DOMException("denied", "NotAllowedError"), "permissionDenied"],
    ["there is no microphone", new DOMException("none", "NotFoundError"), "noMicrophone"],
  ])("should report when %s", async (_d, givenError, expectedError) => {
    // GIVEN the microphone cannot be used
    media.getUserMedia.mockRejectedValueOnce(givenError);
    const { result, onError } = renderVoiceInput();

    // WHEN the user starts recording
    act(() => result.current.start());

    // THEN expect the error
    await waitFor(() => expect(result.current.state).toEqual({ status: "error", error: expectedError }));
    expect(onError).toHaveBeenCalledWith(expectedError);
    // AND the user to be able to try again
    await startRecording(result);
  });

  test.each([
    ["no speech", givenRestAPIError(StatusCodes.UNPROCESSABLE_ENTITY), "noSpeech"],
    ["rate limited", givenRestAPIError(StatusCodes.TOO_MANY_REQUESTS), "rateLimited"],
    ["an upstream failure", givenRestAPIError(StatusCodes.BAD_GATEWAY), "unavailable"],
    ["a network failure", givenRestAPIError(0, ErrorConstants.ErrorCodes.FAILED_TO_FETCH), "network"],
    ["an unexpected failure", new Error("boom"), "unknown"],
  ])("should report %s when transcribing", async (_d, givenError, expectedError) => {
    // GIVEN transcribing fails
    transcribeSpy.mockRejectedValue(givenError);
    const { result, onError, onTranscript } = renderVoiceInput();
    await startRecording(result);

    // WHEN the user stops recording
    act(() => result.current.stop());

    // THEN expect the error
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expectedError));
    expect(result.current.state).toEqual({ status: "error", error: expectedError });
    // AND no transcript
    expect(onTranscript).not.toHaveBeenCalled();
  });

  test("should report no speech for an empty recording, without sending it", async () => {
    // GIVEN the recorder records nothing
    const { result, onError } = renderVoiceInput();
    await startRecording(result);
    FakeMediaRecorder.instances[0].recordedChunks = [];

    // WHEN the user stops recording
    act(() => result.current.stop());

    // THEN expect no speech
    const expectedError = "noSpeech";
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expectedError));
    expect(transcribeSpy).not.toHaveBeenCalled();
  });

  test("should drop the recording when cancelled", async () => {
    // GIVEN the user is recording
    const { result, onTranscript } = renderVoiceInput();
    await startRecording(result);

    // WHEN the recording is cancelled
    act(() => result.current.cancel());

    // THEN expect nothing to be transcribed
    expect(transcribeSpy).not.toHaveBeenCalled();
    expect(onTranscript).not.toHaveBeenCalled();
    expect(result.current.state).toEqual({ status: "idle" });
    // AND the microphone to have been released
    expect(media.streams[0].tracks[0].stop).toHaveBeenCalled();
  });

  test("should abort the transcription when cancelled while transcribing", async () => {
    // GIVEN the recording is being transcribed
    let resolveTranscription: (value: { text: string; locale: string }) => void = () => {};
    transcribeSpy.mockImplementation(() => new Promise((resolve) => (resolveTranscription = resolve)));
    const { result, onTranscript } = renderVoiceInput();
    await startRecording(result);
    act(() => result.current.stop());

    // WHEN it is cancelled, and the transcript arrives later
    act(() => result.current.cancel());
    await act(async () => resolveTranscription({ text: givenTranscript, locale: givenLocale }));

    // THEN expect the request to have been aborted, and the transcript dropped
    expect((transcribeSpy.mock.calls[0][2] as AbortSignal).aborted).toBe(true);
    expect(onTranscript).not.toHaveBeenCalled();
    expect(result.current.state).toEqual({ status: "idle" });
  });

  test("should release the microphone and the audio context on unmount", async () => {
    // GIVEN the user is recording
    const { result, unmount, onTranscript } = renderVoiceInput();
    await startRecording(result);

    // WHEN the field unmounts
    unmount();

    // THEN expect the microphone to be released, the audio context closed, and the animation loop stopped
    expect(media.streams[0].tracks[0].stop).toHaveBeenCalled();
    expect(FakeAudioContext.instances[0].closed).toBe(true);
    expect(animationFrames.size).toBe(0);
    // AND nothing to be transcribed
    expect(transcribeSpy).not.toHaveBeenCalled();
    expect(onTranscript).not.toHaveBeenCalled();
  });

  test("should release the microphone when the recorder fails", async () => {
    // GIVEN the user is recording
    const { result, onError } = renderVoiceInput();
    await startRecording(result);

    // WHEN the recorder fails
    act(() => FakeMediaRecorder.instances[0].onerror?.());

    // THEN expect an error, and the microphone released
    const expectedError = "unknown";
    expect(onError).toHaveBeenCalledWith(expectedError);
    expect(media.streams[0].tracks[0].stop).toHaveBeenCalled();
    expect(FakeAudioContext.instances[0].closed).toBe(true);
  });
});

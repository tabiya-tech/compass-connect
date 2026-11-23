// mute the console
import "src/_test_utilities/consoleMock";

import { act, renderHook, waitFor } from "src/_test_utilities/test-utils";
import { StatusCodes } from "http-status-codes";
import TextToSpeechService from "src/textToSpeech/TextToSpeechService";
import { useTextToSpeech, UseTextToSpeechOptions } from "src/textToSpeech/useTextToSpeech";
import { toPlainText } from "src/textToSpeech/plainText";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";

const givenLocale = "en-US";
const givenMessageId = "message-1";
const givenOtherMessageId = "message-2";
const givenMessage = "Tell me about your work.";

const givenRestAPIError = (statusCode: number, errorCode = ErrorConstants.ErrorCodes.API_ERROR) =>
  new RestAPIError(
    "TextToSpeechService",
    "synthesize",
    "POST",
    "/text-to-speech/synthesize",
    statusCode,
    errorCode,
    "x"
  );

describe("useTextToSpeech", () => {
  let synthesizeSpy: jest.SpyInstance;
  let playSpy: jest.SpyInstance;
  let pauseSpy: jest.SpyInstance;
  let playedAudio: HTMLMediaElement[];
  let createdUrls: string[];
  let revokedUrls: string[];

  beforeEach(() => {
    jest.spyOn(require("src/envService"), "getBackendUrl").mockReturnValue("/api");
    synthesizeSpy = jest
      .spyOn(TextToSpeechService.prototype, "synthesize")
      .mockImplementation(async (text: string) => new Blob([`audio of ${text}`], { type: "audio/mpeg" }));
    playedAudio = [];
    playSpy = jest.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
      playedAudio.push(this);
      return Promise.resolve();
    });
    pauseSpy = jest.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    createdUrls = [];
    revokedUrls = [];
    let counter = 0;
    URL.createObjectURL = jest.fn(() => {
      const url = `blob:audio-${++counter}`;
      createdUrls.push(url);
      return url;
    });
    URL.revokeObjectURL = jest.fn((url: string) => revokedUrls.push(url));
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  const renderPlayer = (options: Partial<UseTextToSpeechOptions> = {}) =>
    renderHook(() => useTextToSpeech({ locale: givenLocale, maxTextBytes: 4000, ...options }));

  const endCurrentAudio = () => act(() => playedAudio[playedAudio.length - 1].dispatchEvent(new Event("ended")));

  test("should load, then play a message, and become idle when it ends", async () => {
    // GIVEN the player
    const { result } = renderPlayer();

    // WHEN a message is played
    act(() => result.current.play(givenMessageId, givenMessage));

    // THEN expect it to be loading
    expect(result.current.state).toEqual({ status: "loading", messageId: givenMessageId });
    // AND then to be playing
    await waitFor(() => expect(result.current.state).toEqual({ status: "playing", messageId: givenMessageId }));
    // AND the text to have been sent once, in the locale
    expect(synthesizeSpy).toHaveBeenCalledTimes(1);
    expect(synthesizeSpy).toHaveBeenCalledWith(givenMessage, givenLocale, expect.any(AbortSignal));

    // AND WHEN the audio ends
    endCurrentAudio();

    // THEN expect the player to be idle
    await waitFor(() => expect(result.current.state).toEqual({ status: "idle" }));
    // AND the audio to have been released
    expect(revokedUrls).toEqual(createdUrls);
  });

  test("should send the message as plain text, without its markdown", async () => {
    // GIVEN the player
    const { result } = renderPlayer();

    // AND a message with markdown
    const givenMarkdown = "**Great!** See [the guide](https://example.org) 🎉\n- Cooking";

    // WHEN it is played
    act(() => result.current.play(givenMessageId, givenMarkdown));

    // THEN expect its plain text to be sent
    await waitFor(() => expect(synthesizeSpy).toHaveBeenCalledTimes(1));
    expect(synthesizeSpy.mock.calls[0][0]).toBe(toPlainText(givenMarkdown));
  });

  test("should stop at once while playing", async () => {
    // GIVEN a message is playing
    const { result } = renderPlayer();
    act(() => result.current.play(givenMessageId, givenMessage));
    await waitFor(() => expect(result.current.state.status).toBe("playing"));

    // WHEN the user stops it
    act(() => result.current.stop());

    // THEN expect the audio to be paused
    expect(pauseSpy).toHaveBeenCalled();
    // AND the player to be idle
    expect(result.current.state).toEqual({ status: "idle" });
    // AND the audio to have been released
    expect(revokedUrls).toEqual(createdUrls);
  });

  test("should stop the message being played when another one is played", async () => {
    // GIVEN a message is playing
    const { result } = renderPlayer();
    act(() => result.current.play(givenMessageId, givenMessage));
    await waitFor(() => expect(result.current.state.status).toBe("playing"));
    const givenFirstSignal: AbortSignal = synthesizeSpy.mock.calls[0][2];

    // WHEN another message is played
    act(() => result.current.play(givenOtherMessageId, givenMessage));

    // THEN expect the first one to have been stopped
    expect(givenFirstSignal.aborted).toBe(true);
    expect(pauseSpy).toHaveBeenCalled();
    // AND the second one to be played
    await waitFor(() => expect(result.current.state).toEqual({ status: "playing", messageId: givenOtherMessageId }));
  });

  test("should abort the request and play nothing when stopped while loading", async () => {
    // GIVEN the audio of a message takes a while
    let resolveAudio: (blob: Blob) => void = () => {};
    synthesizeSpy.mockImplementation(() => new Promise<Blob>((resolve) => (resolveAudio = resolve)));
    const { result } = renderPlayer();
    act(() => result.current.play(givenMessageId, givenMessage));
    expect(result.current.state.status).toBe("loading");

    // WHEN the user stops before it arrives
    act(() => result.current.stop());
    // AND it arrives later
    await act(async () => resolveAudio(new Blob(["late audio"])));

    // THEN expect the request to have been aborted
    expect((synthesizeSpy.mock.calls[0][2] as AbortSignal).aborted).toBe(true);
    // AND nothing to have been played
    expect(playSpy).not.toHaveBeenCalled();
    expect(result.current.state).toEqual({ status: "idle" });
  });

  test("should read a long message in parts, in order", async () => {
    // GIVEN a message longer than the limit of one request
    const givenSentences = ["First part of the message.", "Second part of the message.", "Third part here."];
    const { result } = renderPlayer({ maxTextBytes: 30 });

    // WHEN it is played
    act(() => result.current.play(givenMessageId, givenSentences.join(" ")));

    // THEN expect each part to be played in order as the one before ends
    for (let index = 0; index < givenSentences.length; index++) {
      const expectedPlays = index + 1;
      const actualPlaySpy = playSpy;
      await waitFor(() => expect(actualPlaySpy).toHaveBeenCalledTimes(expectedPlays));
      expect(result.current.state).toEqual({ status: "playing", messageId: givenMessageId });
      endCurrentAudio();
    }
    // AND the parts to have been sent in order
    expect(synthesizeSpy.mock.calls.map((call) => call[0])).toEqual(givenSentences);
    // AND the player to be idle at the end
    await waitFor(() => expect(result.current.state).toEqual({ status: "idle" }));
  });

  test("should not read the next parts when stopped between parts", async () => {
    // GIVEN a long message whose first part is playing
    const { result } = renderPlayer({ maxTextBytes: 30 });
    act(() => result.current.play(givenMessageId, "First part of the message. Second part of the message. Third."));
    await waitFor(() => expect(playSpy).toHaveBeenCalledTimes(1));

    // WHEN the user stops
    act(() => result.current.stop());
    // AND the part fetched ahead arrives
    await act(() => Promise.resolve());

    // THEN expect no other part to be played
    expect(playSpy).toHaveBeenCalledTimes(1);
    // AND the part fetched ahead, at most, to have been requested
    expect(synthesizeSpy.mock.calls.length).toBeLessThanOrEqual(2);
    expect(result.current.state).toEqual({ status: "idle" });
  });

  test.each([
    ["rate limited", givenRestAPIError(StatusCodes.TOO_MANY_REQUESTS), "rateLimited"],
    ["an upstream failure", givenRestAPIError(StatusCodes.BAD_GATEWAY), "unavailable"],
    ["no audio", givenRestAPIError(StatusCodes.UNPROCESSABLE_ENTITY), "unavailable"],
    ["a network failure", givenRestAPIError(0, ErrorConstants.ErrorCodes.FAILED_TO_FETCH), "network"],
    ["an unexpected failure", new Error("boom"), "unknown"],
  ])("should report %s", async (_d, givenError, expectedError) => {
    // GIVEN reading aloud fails
    synthesizeSpy.mockRejectedValue(givenError);
    const givenOnError = jest.fn();
    const { result } = renderPlayer({ onError: givenOnError });

    // WHEN a message is played
    act(() => result.current.play(givenMessageId, givenMessage));

    // THEN expect the error for the message
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "error", messageId: givenMessageId, error: expectedError })
    );
    // AND it to have been reported
    expect(givenOnError).toHaveBeenCalledWith(expectedError);
  });

  test("should report the browser blocking the audio", async () => {
    // GIVEN the browser does not let the audio play
    playSpy.mockRejectedValue(new DOMException("not allowed", "NotAllowedError"));
    const givenOnError = jest.fn();
    const { result } = renderPlayer({ onError: givenOnError });

    // WHEN a message is played
    act(() => result.current.play(givenMessageId, givenMessage));

    // THEN expect an autoplay error
    const expectedError = "autoplayBlocked";
    await waitFor(() => expect(givenOnError).toHaveBeenCalledWith(expectedError));
    expect(result.current.state).toEqual({ status: "error", messageId: givenMessageId, error: expectedError });
    // AND the audio to have been released
    expect(revokedUrls).toEqual(createdUrls);
  });

  test("should report a network error when the device is offline", async () => {
    // GIVEN the device is offline
    jest.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    synthesizeSpy.mockRejectedValue(new Error("offline"));
    const givenOnError = jest.fn();
    const { result } = renderPlayer({ onError: givenOnError });

    // WHEN a message is played
    act(() => result.current.play(givenMessageId, givenMessage));

    // THEN expect a network error
    const expectedError = "network";
    await waitFor(() => expect(givenOnError).toHaveBeenCalledWith(expectedError));
  });

  test("should stop and release the audio when the chat unmounts", async () => {
    // GIVEN a message is playing
    const { result, unmount } = renderPlayer();
    act(() => result.current.play(givenMessageId, givenMessage));
    await waitFor(() => expect(result.current.state.status).toBe("playing"));

    // WHEN the chat unmounts
    unmount();

    // THEN expect the audio to be paused
    expect(pauseSpy).toHaveBeenCalled();
    // AND the request to be aborted
    expect((synthesizeSpy.mock.calls[0][2] as AbortSignal).aborted).toBe(true);
    // AND the audio to have been released
    expect(revokedUrls).toEqual(createdUrls);
  });

  test("should do nothing for a message without text to read", () => {
    // GIVEN the player
    const { result } = renderPlayer();

    // WHEN a message made only of emoji is played
    act(() => result.current.play(givenMessageId, "🎉🎉"));

    // THEN expect nothing to be requested
    expect(synthesizeSpy).not.toHaveBeenCalled();
    expect(result.current.state).toEqual({ status: "idle" });
  });
});

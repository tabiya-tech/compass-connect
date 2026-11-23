// mute the console
import "src/_test_utilities/consoleMock";

import { StatusCodes } from "http-status-codes";
import TextToSpeechService from "src/textToSpeech/TextToSpeechService";
import { setupAPIServiceSpy } from "src/_test_utilities/fetchSpy";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";

describe("TextToSpeechService", () => {
  const givenApiServerUrl = "/path/to/api";
  beforeEach(() => {
    jest.spyOn(require("src/envService"), "getBackendUrl").mockReturnValue(givenApiServerUrl);
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("should get a single instance", () => {
    // WHEN the service is got twice
    const actualFirstInstance = TextToSpeechService.getInstance();
    const actualSecondInstance = TextToSpeechService.getInstance();
    // THEN expect the same instance, for the backend
    expect(actualFirstInstance).toBe(actualSecondInstance);
    expect(actualFirstInstance.apiServerUrl).toBe(givenApiServerUrl);
  });

  test("should post the text and the locale, and return the audio", async () => {
    // GIVEN the backend answers with MP3 audio
    const givenAudio = "mp3-audio-bytes";
    const fetchSpy = setupAPIServiceSpy(StatusCodes.OK, givenAudio, "audio/mpeg");
    // AND a text, a locale and an abort signal
    const givenText = "Tell me about your work.";
    const givenLocale = "en-US";
    const givenSignal = new AbortController().signal;

    // WHEN the text is synthesized
    const actualAudio = await TextToSpeechService.getInstance().synthesize(givenText, givenLocale, givenSignal);

    // THEN expect the audio of the response
    expect(actualAudio.size).toBe(givenAudio.length);
    // AND one POST of the text and the locale, abortable, expecting MP3
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [actualUrl, actualInit] = fetchSpy.mock.calls[0];
    expect(actualUrl).toBe(`${givenApiServerUrl}/text-to-speech/synthesize`);
    expect(actualInit).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ text: givenText, locale: givenLocale }),
        signal: givenSignal,
        expectedStatusCode: StatusCodes.OK,
        expectedContentType: "audio/mpeg",
        compressRequestBody: false,
        retryOnDefaultStatusCodes: false,
      })
    );
  });

  test("should throw the error of the request when it fails", async () => {
    // GIVEN the request fails
    const givenError = new RestAPIError(
      "TextToSpeechService",
      "synthesize",
      "POST",
      "/text-to-speech/synthesize",
      StatusCodes.TOO_MANY_REQUESTS,
      ErrorConstants.ErrorCodes.API_ERROR,
      "rate limited"
    );
    jest.spyOn(require("src/utils/customFetch/customFetch"), "customFetch").mockRejectedValue(givenError);

    // WHEN a text is synthesized
    const actualPromise = TextToSpeechService.getInstance().synthesize("Hello", "en-US");

    // THEN expect the error
    await expect(actualPromise).rejects.toBe(givenError);
  });
});

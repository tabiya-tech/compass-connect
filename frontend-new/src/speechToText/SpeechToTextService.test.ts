// mute the console
import "src/_test_utilities/consoleMock";

import { StatusCodes } from "http-status-codes";
import SpeechToTextService, { baseMimeType } from "src/speechToText/SpeechToTextService";
import { setupAPIServiceSpy } from "src/_test_utilities/fetchSpy";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";

describe("SpeechToTextService", () => {
  const givenApiServerUrl = "/path/to/api";
  beforeEach(() => {
    jest.spyOn(require("src/envService"), "getBackendUrl").mockReturnValue(givenApiServerUrl);
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("should get a single instance", () => {
    // WHEN the service is got twice
    const actualFirstInstance = SpeechToTextService.getInstance();
    const actualSecondInstance = SpeechToTextService.getInstance();
    // THEN expect the same instance, for the backend
    expect(actualFirstInstance).toBe(actualSecondInstance);
    expect(actualFirstInstance.apiServerUrl).toBe(givenApiServerUrl);
  });

  test.each([
    ["audio/webm;codecs=opus", "recording.webm"],
    ["audio/mp4", "recording.mp4"],
    ["audio/ogg;codecs=opus", "recording.ogg"],
    ["", "recording.webm"],
  ])("should upload a %s recording with its locale, and return the transcript", async (givenType, expectedFilename) => {
    // GIVEN the backend answers with a transcript
    const givenResponse = { text: "I worked as a carpenter.", locale: "en-US" };
    const fetchSpy = setupAPIServiceSpy(StatusCodes.OK, givenResponse, "application/json");
    // AND a recording
    const givenRecording = new Blob(["recorded-audio"], { type: givenType });
    const givenSignal = new AbortController().signal;

    // WHEN it is transcribed
    const givenLocale = "en-US";
    const actualResponse = await SpeechToTextService.getInstance().transcribe(givenRecording, givenLocale, givenSignal);

    // THEN expect the transcript
    expect(actualResponse).toEqual(givenResponse);
    // AND one POST of the recording and the locale, abortable, without the default retries
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [actualUrl, actualInit] = fetchSpy.mock.calls[0];
    expect(actualUrl).toBe(`${givenApiServerUrl}/speech-to-text/transcribe`);
    expect(actualInit).toEqual(
      expect.objectContaining({
        method: "POST",
        signal: givenSignal,
        expectedStatusCode: StatusCodes.OK,
        expectedContentType: "application/json",
        compressRequestBody: false,
        retryOnDefaultStatusCodes: false,
      })
    );
    const actualForm: FormData = actualInit.body;
    expect(actualForm.get("locale")).toBe(givenLocale);
    expect((actualForm.get("audio") as File).name).toBe(expectedFilename);
  });

  test("should throw the error of the request when it fails", async () => {
    // GIVEN the request fails
    const givenError = new RestAPIError(
      "SpeechToTextService",
      "transcribe",
      "POST",
      "/speech-to-text/transcribe",
      StatusCodes.UNPROCESSABLE_ENTITY,
      ErrorConstants.ErrorCodes.API_ERROR,
      "no speech"
    );
    jest.spyOn(require("src/utils/customFetch/customFetch"), "customFetch").mockRejectedValue(givenError);

    // WHEN a recording is transcribed
    const actualPromise = SpeechToTextService.getInstance().transcribe(new Blob(["x"]), "en-US");

    // THEN expect the error
    await expect(actualPromise).rejects.toBe(givenError);
  });

  test.each([
    ["audio/webm;codecs=opus", "audio/webm"],
    [" Audio/MP4 ", "audio/mp4"],
  ])("should give %s as %s", (givenMimeType, expectedMimeType) => {
    // WHEN the base type of a media type is taken
    // THEN expect it without its parameters
    expect(baseMimeType(givenMimeType)).toBe(expectedMimeType);
  });
});

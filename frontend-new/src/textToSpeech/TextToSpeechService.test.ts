// mute the console
import "src/_test_utilities/consoleMock";

import TextToSpeechService from "./TextToSpeechService";
import { customFetch } from "src/utils/customFetch/customFetch";
import { StatusCodes } from "http-status-codes";

// Mock dependencies
jest.mock("src/envService", () => ({
  ...jest.requireActual("src/envService"),
  getBackendUrl: jest.fn(() => "https://test-backend.example.com"),
}));

jest.mock("src/utils/customFetch/customFetch", () => ({
  customFetch: jest.fn(),
}));

const mockCustomFetch = customFetch as jest.MockedFunction<typeof customFetch>;

describe("TextToSpeechService", () => {
  const mockCreateObjectURL = jest.fn().mockReturnValue("blob:mock-url");
  const mockRevokeObjectURL = jest.fn();

  beforeEach(() => {
    // Reset the singleton between tests
    (TextToSpeechService as any).instance = undefined;

    jest.clearAllMocks();

    // Mock URL.createObjectURL and URL.revokeObjectURL (not available in jsdom)
    URL.createObjectURL = mockCreateObjectURL;
    URL.revokeObjectURL = mockRevokeObjectURL;
  });

  test("should return a singleton instance", () => {
    // GIVEN two calls to getInstance
    const givenFirstInstance = TextToSpeechService.getInstance();
    const givenSecondInstance = TextToSpeechService.getInstance();

    // THEN expect both calls to return the same instance
    expect(givenFirstInstance).toBe(givenSecondInstance);
  });

  test("should call the backend with the correct payload", async () => {
    // GIVEN a text and language to synthesize
    const givenText = "Hello world";
    const givenLanguage = "en-US";

    // AND the backend returns a valid audio response
    const givenBlob = new Blob(["audio-data"], { type: "audio/mpeg" });
    mockCustomFetch.mockResolvedValue({
      blob: jest.fn().mockResolvedValue(givenBlob),
    } as any);

    // WHEN synthesize is called
    const service = TextToSpeechService.getInstance();
    await service.synthesize(givenText, givenLanguage);

    // THEN expect customFetch to have been called with the correct URL, method, body, and headers
    expect(mockCustomFetch).toHaveBeenCalledWith("https://test-backend.example.com/text-to-speech/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: givenText, language: givenLanguage }),
      expectedStatusCode: StatusCodes.OK,
      serviceName: "TextToSpeechService",
      serviceFunction: "synthesize",
      failureMessage: "Failed to synthesize speech",
      expectedContentType: "audio/mpeg",
      compressRequestBody: false,
    });
  });

  test("should return an object URL from the response blob", async () => {
    // GIVEN a text and language to synthesize
    const givenText = "Hello world";
    const givenLanguage = "en-US";

    // AND the backend returns a valid audio blob
    const givenBlob = new Blob(["audio-data"], { type: "audio/mpeg" });
    mockCustomFetch.mockResolvedValue({
      blob: jest.fn().mockResolvedValue(givenBlob),
    } as any);

    // AND URL.createObjectURL will return a specific URL
    const expectedObjectUrl = "blob:mock-audio-url";
    mockCreateObjectURL.mockReturnValue(expectedObjectUrl);

    // WHEN synthesize is called
    const service = TextToSpeechService.getInstance();
    const actualUrl = await service.synthesize(givenText, givenLanguage);

    // THEN expect URL.createObjectURL to have been called with the blob
    expect(mockCreateObjectURL).toHaveBeenCalledWith(givenBlob);
    // AND expect the returned URL to be the object URL
    expect(actualUrl).toBe(expectedObjectUrl);
  });

  test("should return cached URL on subsequent call with same text and language", async () => {
    // GIVEN a text and language to synthesize
    const givenText = "Hello world";
    const givenLanguage = "en-US";

    // AND the backend returns a valid audio response
    const givenBlob = new Blob(["audio-data"], { type: "audio/mpeg" });
    mockCustomFetch.mockResolvedValue({
      blob: jest.fn().mockResolvedValue(givenBlob),
    } as any);

    const expectedObjectUrl = "blob:mock-cached-url";
    mockCreateObjectURL.mockReturnValue(expectedObjectUrl);

    // AND the first call has already been made
    const service = TextToSpeechService.getInstance();
    const actualFirstUrl = await service.synthesize(givenText, givenLanguage);

    // WHEN synthesize is called again with the same text and language
    const actualSecondUrl = await service.synthesize(givenText, givenLanguage);

    // THEN expect the same URL to be returned
    expect(actualSecondUrl).toBe(actualFirstUrl);
    // AND expect customFetch to have been called only once (not for the cached call)
    expect(mockCustomFetch).toHaveBeenCalledTimes(1);
  });

  test("should propagate error when customFetch rejects", async () => {
    // GIVEN a text and language to synthesize
    const givenText = "Hello world";
    const givenLanguage = "en-US";

    // AND customFetch rejects with an error
    const givenError = new Error("Network failure");
    mockCustomFetch.mockRejectedValue(givenError);

    // WHEN synthesize is called
    const service = TextToSpeechService.getInstance();

    // THEN expect the promise to reject with the same error
    await expect(service.synthesize(givenText, givenLanguage)).rejects.toThrow(givenError);
  });

  test("should evict the oldest entry when cache exceeds max size", async () => {
    // GIVEN a service instance
    const service = TextToSpeechService.getInstance();

    // AND the backend returns a valid audio response for each call
    mockCustomFetch.mockImplementation(() =>
      Promise.resolve({
        blob: jest.fn().mockResolvedValue(new Blob(["audio"], { type: "audio/mpeg" })),
      } as any)
    );

    // AND the cache is filled to the maximum size (20 entries)
    const givenFirstUrl = "blob:url-0";
    mockCreateObjectURL.mockReturnValueOnce(givenFirstUrl);
    await service.synthesize("text-0", "en-US");

    for (let i = 1; i < 20; i++) {
      mockCreateObjectURL.mockReturnValueOnce(`blob:url-${i}`);
      await service.synthesize(`text-${i}`, "en-US");
    }

    // WHEN a 21st entry is added to the cache
    mockCreateObjectURL.mockReturnValueOnce("blob:url-20");
    await service.synthesize("text-20", "en-US");

    // THEN expect URL.revokeObjectURL to have been called for the oldest entry
    expect(mockRevokeObjectURL).toHaveBeenCalledWith(givenFirstUrl);
    // AND expect revokeObjectURL to have been called exactly once (only the first eviction)
    expect(mockRevokeObjectURL).toHaveBeenCalledTimes(1);
  });
});

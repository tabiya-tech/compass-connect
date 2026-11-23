import { StatusCodes } from "http-status-codes";
import { getBackendUrl } from "src/envService";
import { customFetch } from "src/utils/customFetch/customFetch";
import { SynthesizeRequest } from "src/textToSpeech/textToSpeech.types";

export default class TextToSpeechService {
  private static instance: TextToSpeechService;
  readonly apiServerUrl: string;

  private constructor() {
    this.apiServerUrl = getBackendUrl();
  }

  static getInstance(): TextToSpeechService {
    if (!TextToSpeechService.instance) {
      TextToSpeechService.instance = new TextToSpeechService();
    }
    return TextToSpeechService.instance;
  }

  /**
   * Reads a plain text aloud in the voice of its locale.
   *
   * @param text the plain text, within the length limit of the deployment
   * @param locale the locale of the text
   * @param signal aborts the request
   * @return the MP3 audio
   * @throws RestAPIError with the status of the response (429 when rate limited, 502 when the service failed), or
   *   FAILED_TO_FETCH when the request did not reach the backend or was aborted
   */
  async synthesize(text: string, locale: string, signal?: AbortSignal): Promise<Blob> {
    const body: SynthesizeRequest = { text, locale };
    const response = await customFetch(`${this.apiServerUrl}/text-to-speech/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
      expectedStatusCode: StatusCodes.OK,
      serviceName: "TextToSpeechService",
      serviceFunction: "synthesize",
      failureMessage: "Failed to read the message aloud",
      expectedContentType: "audio/mpeg",
      compressRequestBody: false,
      // the backend retries the text-to-speech service itself, and the user is waiting
      retryOnDefaultStatusCodes: false,
    });
    return await response.blob();
  }
}

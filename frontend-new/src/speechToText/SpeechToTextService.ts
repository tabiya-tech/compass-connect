import { StatusCodes } from "http-status-codes";
import { getBackendUrl } from "src/envService";
import { customFetch } from "src/utils/customFetch/customFetch";
import { TranscriptionResponse } from "src/speechToText/speechToText.types";

const FILE_EXTENSIONS: Record<string, string> = {
  "audio/webm": "webm",
  "audio/mp4": "mp4",
  "audio/ogg": "ogg",
};

/** The media type of a recording without its parameters, e.g. "audio/webm;codecs=opus" -> "audio/webm". */
export const baseMimeType = (mimeType: string): string => mimeType.split(";")[0].trim().toLowerCase();

export default class SpeechToTextService {
  private static instance: SpeechToTextService;
  readonly apiServerUrl: string;

  private constructor() {
    this.apiServerUrl = getBackendUrl();
  }

  static getInstance(): SpeechToTextService {
    if (!SpeechToTextService.instance) {
      SpeechToTextService.instance = new SpeechToTextService();
    }
    return SpeechToTextService.instance;
  }

  /**
   * Transcribes a recording of the user, in one request.
   *
   * @param recording the recording, as the browser made it (e.g. audio/webm or audio/mp4)
   * @param locale the locale the user speaks in
   * @param signal aborts the request
   * @return the transcript
   * @throws RestAPIError with the status of the response (422 when no speech was recognized, 429 when rate limited,
   *   502 when the service failed), or FAILED_TO_FETCH when the request did not reach the backend or was aborted
   */
  async transcribe(recording: Blob, locale: string, signal?: AbortSignal): Promise<TranscriptionResponse> {
    const mimeType = baseMimeType(recording.type);
    const formData = new FormData();
    formData.append("audio", recording, `recording.${FILE_EXTENSIONS[mimeType] ?? "webm"}`);
    formData.append("locale", locale);

    const response = await customFetch(`${this.apiServerUrl}/speech-to-text/transcribe`, {
      method: "POST",
      body: formData,
      signal,
      expectedStatusCode: StatusCodes.OK,
      serviceName: "SpeechToTextService",
      serviceFunction: "transcribe",
      failureMessage: "Failed to transcribe the recording",
      expectedContentType: "application/json",
      compressRequestBody: false,
      // the backend retries the speech-to-text service itself, and the user is waiting
      retryOnDefaultStatusCodes: false,
    });
    const body: TranscriptionResponse = JSON.parse(await response.text());
    return body;
  }
}

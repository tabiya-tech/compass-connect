import { getBackendUrl } from "src/envService";
import { StatusCodes } from "http-status-codes";
import { customFetch } from "src/utils/customFetch/customFetch";
import { TranscriptionResponse } from "src/speechToText/SpeechToTextService.types";

function getExtensionForMime(mimeType: string): string {
  const base = mimeType.split(";")[0].trim();
  const map: Record<string, string> = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "video/webm": "webm",
    "video/mp4": "mp4",
  };
  return map[base] || "webm";
}

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

  async transcribe(audioBlob: Blob, language: string): Promise<TranscriptionResponse> {
    const serviceName = "SpeechToTextService";
    const serviceFunction = "transcribe";
    const url = `${this.apiServerUrl}/speech-to-text/transcribe`;

    const formData = new FormData();
    formData.append("audio", audioBlob, `recording.${getExtensionForMime(audioBlob.type)}`);
    formData.append("language", language);

    const response = await customFetch(url, {
      method: "POST",
      body: formData,
      expectedStatusCode: StatusCodes.OK,
      serviceName,
      serviceFunction,
      failureMessage: "Failed to transcribe audio",
      expectedContentType: "application/json",
      compressRequestBody: false,
    });

    const responseBody = await response.text();
    return JSON.parse(responseBody) as TranscriptionResponse;
  }
}
